"""
main_pi.py — Raspberry Pi printer WebSocket service.

Run with:
    uvicorn main:app --host 0.0.0.0 --port 8001 --reload

WebSocket endpoint: ws://<pi-host>:8001/ws

Movement limits (soft, checked before G-code is sent):
    X :   0 … 252 mm
    Y : -19 … 221 mm
    Z :   0 … 275 mm
    E : unlimited

Z-axis inversion:
    This machine's Z motor is physically inverted.
    G1 Z+N  →  nozzle moves DOWN  (toward bed)
    G1 Z-N  →  nozzle moves UP    (away from bed)

Limit switch safety loop:
    A background asyncio task polls all GPIO limit switches every 50 ms.
    When a switch triggers:
      - M410 (quickstop) is sent to the firmware immediately.
      - The axis is flagged as blocked in the negative direction.
      - Any further move command that would move toward that limit is rejected
        until the axis is jogged away from the switch (switch releases).
      - A "limit_triggered" event is pushed to all connected WebSocket clients.
"""

import asyncio
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from printer import Printer, PrinterConfig, PrinterNotConnectedError, PrinterTimeoutError
from gpio_manager import (
    init_gpio,
    cleanup_gpio,
    read_limit_switches,
    is_triggered,
    gpio_available,
    LIMIT_SWITCH_PINS,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("printer_pi")


# ---------------------------------------------------------------------------
# Thread pool + printer singleton
# ---------------------------------------------------------------------------

_executor = ThreadPoolExecutor(max_workers=4)
_printer  = Printer()


async def _run(fn, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, fn, *args)


# ---------------------------------------------------------------------------
# Connected WebSocket clients  (for pushing limit-trigger events)
# ---------------------------------------------------------------------------

_ws_clients: set[WebSocket] = set()


async def _push_event(event: dict) -> None:
    """Broadcast a JSON event to all connected WebSocket clients."""
    msg = json.dumps(event)
    dead = set()
    for ws in _ws_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    _ws_clients.difference_update(dead)


# ---------------------------------------------------------------------------
# Software position tracker
# ---------------------------------------------------------------------------

_soft_position: dict[str, float] = {"X": 0.0, "Y": 0.0, "Z": 0.0, "E": 0.0}
_homed:         dict[str, bool]  = {"X": False, "Y": False, "Z": False}


# ---------------------------------------------------------------------------
# Limit switch state  —  updated by the background watcher loop
#
# _switch_blocked["X_MIN"] = True  means X cannot move in the negative
# direction until the switch releases.
# ---------------------------------------------------------------------------

_switch_blocked: dict[str, bool] = {name: False for name in LIMIT_SWITCH_PINS}

# Map switch name → (axis, sign_blocked)
# sign_blocked = -1 means "negative moves on this axis are blocked"
_SWITCH_AXIS_MAP: dict[str, tuple[str, int]] = {
    "X_MIN": ("X", -1),
    "Y_MIN": ("Y", -1),
    "Z_MIN": ("Z", -1),
}

GPIO_POLL_INTERVAL = 0.05   # seconds between GPIO reads


async def _limit_switch_watcher() -> None:
    """
    Background task: polls all limit switches every GPIO_POLL_INTERVAL seconds.

    On trigger:
      1. Sends M410 quickstop to the printer (if connected).
      2. Sets the axis as blocked in that direction.
      3. Pushes a "limit_triggered" event to all WebSocket clients.

    On release:
      1. Clears the blocked flag.
      2. Pushes a "limit_released" event to all WebSocket clients.
    """
    log.info("Limit switch watcher started  poll=%.0f ms", GPIO_POLL_INTERVAL * 1000)

    # previous state so we only act on edges (not every poll)
    prev: dict[str, bool] = {name: False for name in LIMIT_SWITCH_PINS}

    while True:
        await asyncio.sleep(GPIO_POLL_INTERVAL)

        if not gpio_available():
            continue

        current = read_limit_switches()

        for switch_name, triggered in current.items():
            was_triggered = prev.get(switch_name, False)

            # ── Rising edge: switch just triggered ────────────────────
            if triggered and not was_triggered:
                _switch_blocked[switch_name] = True
                axis_info = _SWITCH_AXIS_MAP.get(switch_name, ("?", 0))
                log.warning(
                    "LIMIT TRIGGERED  switch=%s  axis=%s  direction=%s",
                    switch_name, axis_info[0],
                    "negative" if axis_info[1] < 0 else "positive",
                )

                # Send quickstop to firmware
                if _printer.is_connected:
                    try:
                        await _run(_printer.send_gcode, "M410")
                        log.warning("M410 quickstop sent")
                    except Exception as exc:
                        log.error("Failed to send M410: %s", exc)

                await _push_event({
                    "type":   "limit_triggered",
                    "switch": switch_name,
                    "axis":   axis_info[0],
                    "direction": "negative" if axis_info[1] < 0 else "positive",
                })

            # ── Falling edge: switch just released ────────────────────
            elif not triggered and was_triggered:
                _switch_blocked[switch_name] = False
                log.info("LIMIT RELEASED  switch=%s", switch_name)
                await _push_event({
                    "type":   "limit_released",
                    "switch": switch_name,
                })

        prev = current


def _check_limit_switches(axis: str, delta_mm: float) -> tuple[bool, str]:
    """
    Return (False, reason) if a limit switch is blocking this move.
    A move is blocked when:
      - The switch for this axis is triggered (blocked flag is set), AND
      - The requested move is in the same direction as the switch (negative).
    """
    for switch_name, (sw_axis, sw_sign) in _SWITCH_AXIS_MAP.items():
        if sw_axis != axis:
            continue
        if not _switch_blocked.get(switch_name, False):
            continue
        # Switch is triggered — only block moves that go further into the limit
        if (sw_sign < 0 and delta_mm < 0) or (sw_sign > 0 and delta_mm > 0):
            msg = (
                f"Move rejected: {axis} limit switch '{switch_name}' is triggered. "
                f"Jog away from the limit before moving in this direction."
            )
            log.warning("SWITCH BLOCK  %s", msg)
            return False, msg
    return True, ""


# ---------------------------------------------------------------------------
# Movement limits (soft)
# ---------------------------------------------------------------------------

_LIMITS: dict[str, tuple[Optional[float], Optional[float]]] = {
    "X": (10.0,   245.0),
    "Y": (-10.0,  210.0),
    "Z": (10.0,   265.0),
    "E": (None,   None),
}


def _limits_check(axis: str, current_mm: float, delta_mm: float) -> tuple[bool, str]:
    lo, hi = _LIMITS.get(axis, (None, None))
    target = current_mm + delta_mm

    if lo is not None and target < lo:
        if current_mm <= lo and target > current_mm:
            pass  # escape toward safe zone — allow
        else:
            msg = (
                f"Move rejected: {axis} target {target:.2f} mm is below "
                f"minimum {lo:.0f} mm (current: {current_mm:.2f} mm)."
            )
            log.warning("LIMIT BREACH  %s", msg)
            return False, msg

    if hi is not None and target > hi:
        if current_mm >= hi and target < current_mm:
            pass  # escape toward safe zone — allow
        else:
            msg = (
                f"Move rejected: {axis} target {target:.2f} mm exceeds "
                f"maximum {hi:.0f} mm (current: {current_mm:.2f} mm)."
            )
            log.warning("LIMIT BREACH  %s", msg)
            return False, msg

    return True, ""


# ---------------------------------------------------------------------------
# Homing  —  drives motor toward switch, stops when GPIO triggers
# ---------------------------------------------------------------------------

# Step size per homing move (mm) — small so we stop close to the switch
HOMING_STEP_MM      = 2.0
HOMING_FEED_XY      = 800    # mm/min — slow for safety
HOMING_FEED_Z       = 400
HOMING_MAX_TRAVEL   = 350.0  # mm — give up if switch never triggers


async def _home_single_axis(axis: str) -> dict:
    """
    Drive *axis* in the negative direction in HOMING_STEP_MM increments
    until the limit switch triggers, then stop and declare position = 0.

    The watcher loop is paused for this axis during homing to avoid
    double-handling the trigger event.
    """
    switch_name = f"{axis}_MIN"

    if not gpio_available():
        raise RuntimeError(
            "GPIO is not available. Homing requires limit switches on the Pi GPIO pins."
        )

    if not _printer.is_connected:
        raise PrinterNotConnectedError("Printer is not connected. Connect first before homing.")

    feed         = HOMING_FEED_Z if axis == "Z" else HOMING_FEED_XY
    total_travel = 0.0

    log.info("HOMING START  axis=%s  switch=%s  step=%.1f mm  feed=%d", axis, switch_name, HOMING_STEP_MM, feed)

    # If already triggered at the start, back off first so we get a clean edge
    if is_triggered(switch_name):
        log.info("HOMING  switch already triggered — backing off 5 mm first")
        await _run(_printer.move, axis, +5.0, feed)
        await asyncio.sleep(0.1)

    # Drive toward the switch in small steps, polling GPIO after each move
    while not is_triggered(switch_name):
        if total_travel >= HOMING_MAX_TRAVEL:
            raise RuntimeError(
                f"Homing {axis} failed: switch '{switch_name}' never triggered "
                f"after {total_travel:.0f} mm. Check wiring or increase HOMING_MAX_TRAVEL."
            )

        log.debug("HOMING STEP  axis=%s  traveled=%.1f mm", axis, total_travel)
        await _run(_printer.move, axis, -HOMING_STEP_MM, feed)
        total_travel += HOMING_STEP_MM

        # Small yield so the event loop stays alive
        await asyncio.sleep(0.01)

    # Switch triggered — stop immediately
    log.warning("HOMING  switch triggered  axis=%s  travel=%.1f mm", axis, total_travel)

    # Update state: position is 0, axis is homed
    _soft_position[axis]          = 0.0
    _homed[axis]                  = True
    _switch_blocked[switch_name]  = True   # respect the triggered state

    log.info("HOMING COMPLETE  axis=%s  position set to 0.0", axis)

    await _push_event({
        "type":   "homing_complete",
        "axis":   axis,
        "switch": switch_name,
        "travel_mm": round(total_travel, 2),
    })

    return {
        "axis":         axis,
        "switch":       switch_name,
        "travel_mm":    round(total_travel, 2),
        "position_set": 0.0,
    }


async def _home_axes(axes: list[str]) -> dict:
    """Home multiple axes in safe order: Z first, then X, then Y."""
    safe_order = [ax for ax in ("Z", "X", "Y") if ax in axes]
    return {axis: await _home_single_axis(axis) for axis in safe_order}


# ---------------------------------------------------------------------------
# Auto-reconnect loop
# ---------------------------------------------------------------------------

RECONNECT_INTERVAL = 10.0  # seconds between auto-reconnect attempts
_printer_connect_lock = asyncio.Lock()

async def _reconnect_loop() -> None:
    """
    Background task: watches the serial connection and retries automatically
    whenever it is lost.  Pushes "printer_connected" / "printer_disconnected"
    events to all WebSocket clients on state changes.
    """
    log.info("Auto-reconnect loop started  interval=%.0f s", RECONNECT_INTERVAL)
    was_connected = False

    while True:
        await asyncio.sleep(RECONNECT_INTERVAL)

        now_connected = _printer.is_connected

        # ── Connection lost ───────────────────────────────────────────
        if was_connected and not now_connected:
            log.warning("PRINTER DISCONNECTED — will retry every %.0f s", RECONNECT_INTERVAL)
            await _push_event({"type": "printer_disconnected"})

        # ── Not connected — try to reconnect ─────────────────────────
        if not now_connected:
            # Skip if a manual connect request is already in progress.
            if _printer_connect_lock.locked():
                log.debug("RECONNECT skipped — manual connect in progress")
                continue
            try:
                # Use wait_for so this attempt does not hold the lock past the
                # next RECONNECT_INTERVAL — a manual connect can then proceed.
                await asyncio.wait_for(_printer_connect_lock.acquire(), timeout=5.0)
            except asyncio.TimeoutError:
                log.debug("RECONNECT skipped — could not acquire connect lock")
                continue
            try:
                log.info("RECONNECT ATTEMPT  port=%s", _printer.config.port)
                await _run(_printer.connect)
                log.info("RECONNECT SUCCESS  port=%s", _printer.config.port)
                await _push_event({"type": "printer_connected", "port": _printer.config.port})
                was_connected = True
            except Exception as exc:
                log.debug("RECONNECT FAILED  %s", exc)
                was_connected = False
            finally:
                _printer_connect_lock.release()
        else:
            was_connected = True


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=== Printer service starting ===")
    init_gpio()
    watcher     = asyncio.create_task(_limit_switch_watcher())
    reconnecter = asyncio.create_task(_reconnect_loop())
    yield
    log.info("=== Printer service shutting down ===")
    watcher.cancel()
    reconnecter.cancel()
    if _printer.is_connected:
        _printer.disconnect()
        log.info("Serial port closed.")
    cleanup_gpio()
    _executor.shutdown(wait=False)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Printer Control Service",
    description="WebSocket G-code bridge for a Marlin printer (Raspberry Pi).",
    version="2.4.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {
        "ok":        True,
        "connected": _printer.is_connected,
        "port":      _printer.config.port,
        "baud_rate": _printer.config.baud_rate,
        "gpio":      gpio_available(),
    }


@app.get("/gpio/limits")
async def get_limit_switches():
    return {
        "ok":      True,
        "gpio":    gpio_available(),
        "switches": read_limit_switches(),
        "blocked":  dict(_switch_blocked),
    }


# ---------------------------------------------------------------------------
# Action dispatcher
# ---------------------------------------------------------------------------

async def _dispatch(action: str, params: dict) -> dict:

    log.info("DISPATCH  action=%s  params=%s", action, params)

    # ── Connection ────────────────────────────────────────────────────────

    if action == "connect":
        valid  = set(PrinterConfig.__dataclass_fields__)
        fields = {k: v for k, v in params.items() if k in valid}

        # If already connected and no config override requested, return immediately
        # instead of re-opening the serial port (which blocks for ~2 s + Marlin banner).
        if _printer.is_connected and not fields:
            log.info("Serial port already open  port=%s  (skipping re-connect)", _printer.config.port)
            return {"connected": True, "port": _printer.config.port, "baud_rate": _printer.config.baud_rate}

        # Acquire the connect lock with a generous timeout so we never block a
        # WebSocket handler indefinitely when the auto-reconnect loop holds the lock.
        try:
            await asyncio.wait_for(_printer_connect_lock.acquire(), timeout=25.0)
        except asyncio.TimeoutError:
            raise RuntimeError(
                "connect: timed out waiting for printer_connect_lock "
                "(auto-reconnect loop may be in progress — try again shortly)"
            )
        try:
            _printer.config = PrinterConfig(**fields) if fields else PrinterConfig()
            await _run(_printer.connect)
        finally:
            _printer_connect_lock.release()

        log.info("Serial port OPEN  port=%s", _printer.config.port)
        return {"connected": True, "port": _printer.config.port, "baud_rate": _printer.config.baud_rate}

    if action == "disconnect":
        await _run(_printer.disconnect)
        return {"connected": False}

    if action == "status":
        return {
            "connected":     _printer.is_connected,
            "port":          _printer.config.port,
            "baud_rate":     _printer.config.baud_rate,
            "feed_xy":       _printer.config.feed_xy,
            "feed_z":        _printer.config.feed_z,
            "feed_e":        _printer.config.feed_e,
            "limits":        {ax: {"min": lo, "max": hi} for ax, (lo, hi) in _LIMITS.items()},
            "gpio":          gpio_available(),
            "switches":      read_limit_switches(),
            "blocked":       dict(_switch_blocked),
            "soft_position": dict(_soft_position),
            "homed":         dict(_homed),
        }

    # ── Motion ───────────────────────────────────────────────────────────

    if action == "move":
        axis     = str(params["axis"]).upper()
        distance = float(params["distance"])
        feed     = params.get("feed")

        if axis not in ("X", "Y", "Z", "E"):
            raise ValueError(f"Unknown axis '{axis}'. Must be X, Y, Z or E.")

        firmware_delta = distance

        # 1. Check GPIO limit switches first
        ok, warning = _check_limit_switches(axis, firmware_delta)
        if not ok:
            return {"moved": False, "warning": warning}

        # 2. Check soft limits
        pos     = await _run(_printer.get_position)
        current = getattr(pos, axis, 0.0)
        ok, warning = _limits_check(axis, current, firmware_delta)
        if not ok:
            return {"moved": False, "warning": warning}

        eff_feed = feed or _printer._default_feed(axis)
        await _run(_printer.move, axis, firmware_delta, feed)

        _soft_position[axis] = round(current + firmware_delta, 3)
        log.info("MOVE COMPLETE  axis=%s  soft_pos=%.3f", axis, _soft_position[axis])

        return {
            "moved":          True,
            "axis":           axis,
            "distance_mm":    distance,
            "firmware_delta": firmware_delta,
            "new_pos_approx": _soft_position[axis],
            "feed":           eff_feed,
        }

    if action == "move_up":
        distance = float(params.get("distance", 1.0))
        feed     = int(params.get("feed", 1200))

        firmware_delta = -distance

        ok, warning = _check_limit_switches("Z", firmware_delta)
        if not ok:
            return {"moved": False, "warning": warning}

        pos       = await _run(_printer.get_position)
        current_z = pos.Z
        ok, warning = _limits_check("Z", current_z, firmware_delta)
        if not ok:
            return {"moved": False, "warning": warning}

        await _run(_printer.move, "Z", firmware_delta, feed)
        _soft_position["Z"] = round(current_z + firmware_delta, 3)

        return {
            "moved":          True,
            "axis":           "Z",
            "distance_mm":    distance,
            "firmware_delta": firmware_delta,
            "new_pos_approx": _soft_position["Z"],
            "feed":           feed,
        }

    # ── Homing ───────────────────────────────────────────────────────────

    if action == "home":
        raw_axes = params.get("axes")
        if raw_axes is None:
            axes = ["X", "Y", "Z"]
        elif isinstance(raw_axes, str):
            axes = [raw_axes.upper()]
        else:
            axes = [str(a).upper() for a in raw_axes]

        invalid = [a for a in axes if a not in ("X", "Y", "Z")]
        if invalid:
            raise ValueError(f"Cannot home unknown axes: {invalid}.")

        results = await _home_axes(axes)
        return {"homed": True, "axes": axes, "results": results, "soft_position": dict(_soft_position)}

    # ── Limit switch state ────────────────────────────────────────────────

    if action == "limit_switches":
        return {
            "gpio":          gpio_available(),
            "switches":      read_limit_switches(),
            "blocked":       dict(_switch_blocked),
            "homed":         dict(_homed),
            "soft_position": dict(_soft_position),
        }

    # ── Sensors ──────────────────────────────────────────────────────────

    if action == "position":
        pos = await _run(_printer.get_position)
        return pos.as_dict()

    if action == "temperature":
        return await _run(_printer.get_temperature)

    if action == "gcode":
        command = str(params["command"])
        timeout = params.get("timeout")
        lines   = await _run(_printer.send_gcode, command, timeout)
        return {"command": command, "response": lines}

    if action == "emergency_stop":
        log.critical("EMERGENCY STOP — M112")
        await _run(_printer.emergency_stop)
        return {"stopped": True}

    if action == "printer_status":
        if not _printer.is_connected:
            return {
                "connected":     False,
                "position":      {"X": 0.0, "Y": 0.0, "Z": 0.0, "E": 0.0},
                "temperatures":  {"hotend_temp": None, "bed_temp": None},
                "switches":      read_limit_switches(),
                "blocked":       dict(_switch_blocked),
                "soft_position": dict(_soft_position),
                "homed":         dict(_homed),
            }
        # Run M114 (position) and M105 (temperature) as a single serial
        # round-trip to avoid two sequential 5 s timeouts.
        pos, temp = await _run(_printer.get_status_combined)
        return {
            "connected":     True,
            "position":      pos.as_dict(),
            "temperatures":  {"hotend_temp": temp["hotend_temp"], "bed_temp": temp["bed_temp"]},
            "switches":      read_limit_switches(),
            "blocked":       dict(_switch_blocked),
            "soft_position": dict(_soft_position),
            "homed":         dict(_homed),
        }

    raise ValueError(f"Unknown action: '{action}'")


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.add(websocket)
    log.info("WS CLIENT CONNECTED  remote=%s", websocket.client)

    # Lock so concurrent tasks don't interleave send_text frames on the same socket.
    _send_lock = asyncio.Lock()

    async def _handle_one(msg_id: str, action: str, params: dict) -> None:
        """Dispatch a single action and send the response — runs as an independent task."""
        try:
            data  = await _dispatch(action, params)
            reply = json.dumps({"id": msg_id, "status": "ok", "data": data})
        except PrinterNotConnectedError as exc:
            reply = json.dumps({"id": msg_id, "status": "error", "detail": str(exc), "code": 503})
        except PrinterTimeoutError as exc:
            reply = json.dumps({"id": msg_id, "status": "error", "detail": str(exc), "code": 504})
        except (ValueError, KeyError) as exc:
            reply = json.dumps({"id": msg_id, "status": "error", "detail": str(exc), "code": 422})
        except RuntimeError as exc:
            reply = json.dumps({"id": msg_id, "status": "error", "detail": str(exc), "code": 500})
        except Exception as exc:
            log.exception("UNEXPECTED ERROR  action=%s", action)
            reply = json.dumps({"id": msg_id, "status": "error", "detail": str(exc), "code": 500})
        try:
            # Serialise writes so concurrent tasks don't corrupt the WebSocket frame stream.
            async with _send_lock:
                await websocket.send_text(reply)
        except Exception:
            pass  # client disconnected before reply could be sent

    try:
        while True:
            raw_msg = await websocket.receive_text()
            log.debug("WS RECV  %s", raw_msg[:300])

            try:
                msg    = json.loads(raw_msg)
                action = msg.get("action", "")
                params = msg.get("params") or {}
                msg_id = msg.get("id", "")
            except json.JSONDecodeError as exc:
                async with _send_lock:
                    await websocket.send_text(json.dumps({
                        "id": None, "status": "error", "detail": f"Invalid JSON: {exc}", "code": 400,
                    }))
                continue

            # Fire-and-forget: each action runs concurrently so a slow serial
            # command (move, home, gcode) never blocks a lightweight status poll.
            asyncio.create_task(_handle_one(msg_id, action, params))

    except WebSocketDisconnect:
        log.info("WS CLIENT DISCONNECTED  remote=%s", websocket.client)
    except Exception as exc:
        log.exception("WS ENDPOINT CRASHED  %s", exc)
    finally:
        _ws_clients.discard(websocket)