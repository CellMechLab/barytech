"""
main_pi.py — Raspberry Pi printer WebSocket service.

Run with:
    uvicorn main_pi:app --host 0.0.0.0 --port 8001 --reload

WebSocket endpoint: ws://<pi-host>:8001/ws

Movement limits enforced here (soft limits, before any G-code is sent):
    X :   0 … 252 mm
    Y : -19 … 221 mm
    Z :   0 … 275 mm
    E : unlimited

Z-axis inversion:
    This machine's Z motor is physically inverted.
    G1 Z+N  →  nozzle moves DOWN  (toward bed)
    G1 Z-N  →  nozzle moves UP    (away from bed)
    All callers use the intuitive convention (positive = up).
    This file negates Z before sending to firmware.
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

# ---------------------------------------------------------------------------
# Logging setup  — outputs to stdout so uvicorn captures it
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

_executor = ThreadPoolExecutor(max_workers=1)   # one serial command at a time
_printer  = Printer()


async def _run(fn, *args):
    """Offload a blocking serial call to the single-worker thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, fn, *args)


# ---------------------------------------------------------------------------
# Movement limits
# ---------------------------------------------------------------------------

_LIMITS: dict[str, tuple[Optional[float], Optional[float]]] = {
    "X": (10.0,   245.0),
    "Y": (-10.0,  210.0),
    "Z": (10.0,   265.0),
    "E": (None,   None),     # no limit on extruder
}


def _limits_check(axis: str, current_mm: float, delta_mm: float) -> tuple[bool, str]:
    """
    Return (True, "") if the move is within limits.
    Return (False, "<reason>") if it would breach a limit.

    *delta_mm* must use the user-facing convention (positive Z = up).
    """
    lo, hi = _LIMITS.get(axis, (None, None))
    target = current_mm + delta_mm

    log.debug(
        "LIMITS CHECK  axis=%s  current=%.3f  delta=%.3f  target=%.3f  "
        "limit=[%s, %s]",
        axis, current_mm, delta_mm, target,
        f"{lo:.0f}" if lo is not None else "-inf",
        f"{hi:.0f}" if hi is not None else "+inf",
    )

    if lo is not None and target < lo:
        # Allow the move if we are already below the minimum and the move
        # brings us closer to (or back inside) the safe range.
        if current_mm <= lo and target > current_mm:
            log.debug(
                "LIMITS ESCAPE  axis=%s already below min %.0f, "
                "allowing move toward safe zone (target=%.3f)",
                axis, lo, target,
            )
        else:
            msg = (
                f"Move rejected: {axis} target {target:.2f} mm is below "
                f"minimum {lo:.0f} mm (current: {current_mm:.2f} mm)."
            )
            log.warning("LIMIT BREACH  %s", msg)
            return False, msg

    if hi is not None and target > hi:
        # Allow the move if we are already above the maximum and the move
        # brings us closer to (or back inside) the safe range.
        if current_mm >= hi and target < current_mm:
            log.debug(
                "LIMITS ESCAPE  axis=%s already above max %.0f, "
                "allowing move toward safe zone (target=%.3f)",
                axis, hi, target,
            )
        else:
            msg = (
                f"Move rejected: {axis} target {target:.2f} mm exceeds "
                f"maximum {hi:.0f} mm (current: {current_mm:.2f} mm)."
            )
            log.warning("LIMIT BREACH  %s", msg)
            return False, msg

    log.debug("LIMITS OK  axis=%s  target=%.3f", axis, target)
    return True, ""


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=== Printer service starting ===")
    yield
    log.info("=== Printer service shutting down ===")
    if _printer.is_connected:
        _printer.disconnect()
        log.info("Serial port closed.")
    _executor.shutdown(wait=False)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Printer Control Service",
    description="WebSocket G-code bridge for a Marlin printer (Raspberry Pi).",
    version="2.2.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# HTTP health check
# ---------------------------------------------------------------------------

@app.get("/health", summary="Health / printer connection status")
async def health():
    return {
        "ok":        True,
        "connected": _printer.is_connected,
        "port":      _printer.config.port,
        "baud_rate": _printer.config.baud_rate,
    }


# ---------------------------------------------------------------------------
# Action dispatcher
# ---------------------------------------------------------------------------

async def _dispatch(action: str, params: dict) -> dict:
    """
    Route an action string to the appropriate Printer method.

    Returns a plain dict (becomes the 'data' field of the response frame).
    Raises PrinterNotConnectedError / PrinterTimeoutError / ValueError on failure.
    """

    log.info("DISPATCH  action=%s  params=%s", action, params)

    # ── Connection management ─────────────────────────────────────────────

    if action == "connect":
        valid  = set(PrinterConfig.__dataclass_fields__)
        fields = {k: v for k, v in params.items() if k in valid}
        _printer.config = PrinterConfig(**fields) if fields else PrinterConfig()
        log.info("Connecting to serial port %s @ %d baud …",
                 _printer.config.port, _printer.config.baud_rate)
        await _run(_printer.connect)
        log.info("Serial port OPEN  port=%s", _printer.config.port)
        return {
            "connected": True,
            "port":      _printer.config.port,
            "baud_rate": _printer.config.baud_rate,
        }

    if action == "disconnect":
        log.info("Disconnecting serial port …")
        await _run(_printer.disconnect)
        log.info("Serial port CLOSED")
        return {"connected": False}

    if action == "status":
        status = {
            "connected": _printer.is_connected,
            "port":      _printer.config.port,
            "baud_rate": _printer.config.baud_rate,
            "feed_xy":   _printer.config.feed_xy,
            "feed_z":    _printer.config.feed_z,
            "feed_e":    _printer.config.feed_e,
            "limits":    {ax: {"min": lo, "max": hi}
                          for ax, (lo, hi) in _LIMITS.items()},
        }
        log.debug("STATUS  %s", status)
        return status

    # ── Motion ──────────────────────────────────────────────────────────

    if action == "move":
        axis     = str(params["axis"]).upper()
        distance = float(params["distance"])
        feed     = params.get("feed")

        if axis not in ("X", "Y", "Z", "E"):
            raise ValueError(f"Unknown axis '{axis}'. Must be X, Y, Z or E.")

        # ------------------------------------------------------------------
        # Z-AXIS INVERSION
        # ------------------------------------------------------------------
        # Physical reality on this machine:
        #   G1 Z+N (relative)  →  nozzle moves DOWN toward bed  (firmware Z increases)
        #   G1 Z-N (relative)  →  nozzle moves UP  away from bed (firmware Z decreases)
        #
        # User/caller convention:
        #   distance < 0  →  nozzle UP  (away from bed)   e.g. distance = -10
        #   distance > 0  →  nozzle DOWN (toward bed)     e.g. distance = +10
        #
        # Because negative distance maps to G1 Z-N (nozzle UP), the user
        # convention matches the firmware convention directly — NO negation.
        # X and Y are also passed straight through.
        # ------------------------------------------------------------------
        firmware_delta = distance   # no sign flip needed for any axis

        log.info(
            "MOVE %s  distance=%.3f  firmware_delta=%.3f  "
            "[G1 %s%+g will be sent to printer]",
            axis, distance, firmware_delta, axis, firmware_delta,
        )

        # ── Read current position for limits check ─────────────────────
        pos     = await _run(_printer.get_position)
        current = getattr(pos, axis, 0.0)
        log.info("POSITION BEFORE MOVE  %s", pos.as_dict())

        # ── Limits check — always use firmware_delta (actual motor direction) ──
        ok, warning = _limits_check(axis, current, firmware_delta)
        if not ok:
            return {"moved": False, "warning": warning}

        # ── Send to firmware ───────────────────────────────────────────
        eff_feed = feed or _printer._default_feed(axis)
        log.info(
            "GCODE SEQUENCE  G91 -> G1 %s%+g F%g -> M400 -> G90",
            axis, firmware_delta, eff_feed,
        )
        await _run(_printer.move, axis, firmware_delta, feed)
        log.info("MOVE COMPLETE  axis=%s", axis)

        return {
            "moved":          True,
            "axis":           axis,
            "distance_mm":    distance,
            "firmware_delta": firmware_delta,
            "new_pos_approx": round(current + firmware_delta, 3),
            "feed":           eff_feed,
        }

    if action == "move_up":
        # Convenience: raise the nozzle by *distance* mm (positive = up).
        # "Up" on this inverted Z motor = G1 Z-N = negative firmware delta.
        distance = float(params.get("distance", 1.0))
        feed     = int(params.get("feed", 1200))

        log.info("MOVE_UP  distance=%.3f  feed=%d", distance, feed)

        pos       = await _run(_printer.get_position)
        current_z = pos.Z
        log.info("POSITION BEFORE MOVE_UP  %s", pos.as_dict())

        # Negate for inverted Z motor: nozzle UP = firmware Z decreases.
        firmware_delta = -distance

        # Limits check must use firmware_delta so the escape logic works
        # correctly when Z is already above the maximum (over-travel recovery).
        ok, warning = _limits_check("Z", current_z, firmware_delta)
        if not ok:
            return {"moved": False, "warning": warning}

        log.info(
            "GCODE SEQUENCE (move_up)  G91 -> G1 Z%+g F%d -> M400 -> G90",
            firmware_delta, feed,
        )
        await _run(_printer.move, "Z", firmware_delta, feed)
        log.info("MOVE_UP COMPLETE")

        return {
            "moved":          True,
            "axis":           "Z",
            "distance_mm":    distance,
            "firmware_delta": firmware_delta,
            "new_pos_approx": round(current_z + firmware_delta, 3),
            "feed":           feed,
        }

    # ── Home (DISABLED) ───────────────────────────────────────────────────
    # Uncomment to re-enable homing.
    #
    # if action == "home":
    #     axes = params.get("axes")
    #     log.info("HOMING  axes=%s", axes or "ALL")
    #     await _run(_printer.home, axes)
    #     log.info("HOMING COMPLETE")
    #     return {"homed": True, "axes": axes or ["X", "Y", "Z"]}

    # ── Sensors ──────────────────────────────────────────────────────────

    if action == "position":
        pos = await _run(_printer.get_position)
        log.debug("POSITION  %s", pos.as_dict())
        return pos.as_dict()

    if action == "temperature":
        temp = await _run(_printer.get_temperature)
        log.debug("TEMPERATURE  hotend=%s  bed=%s",
                  temp.get("hotend_temp"), temp.get("bed_temp"))
        return temp

    # ── Extruder (disabled) ───────────────────────────────────────────────

    # if action == "extrude":
    #     distance = float(params["distance"])
    #     feed     = params.get("feed")
    #     await _run(_printer.move, "E", +distance, feed)
    #     return {"extruded_mm": distance}

    # if action == "retract":
    #     distance = float(params["distance"])
    #     feed     = params.get("feed")
    #     await _run(_printer.move, "E", -distance, feed)
    #     return {"retracted_mm": distance}

    # ── Advanced ─────────────────────────────────────────────────────────

    if action == "gcode":
        command = str(params["command"])
        timeout = params.get("timeout")
        log.info("RAW GCODE  command=%r  timeout=%s", command, timeout)
        lines = await _run(_printer.send_gcode, command, timeout)
        log.info("RAW GCODE RESPONSE  %s", lines)
        return {"command": command, "response": lines}

    if action == "emergency_stop":
        log.critical("EMERGENCY STOP TRIGGERED — M112 sent to firmware")
        await _run(_printer.emergency_stop)
        return {"stopped": True, "note": "Printer firmware halted. Reboot required."}

    # ── Combined status (used by PC dashboard push loop) ─────────────────

    if action == "printer_status":
        pos  = await _run(_printer.get_position)
        temp = await _run(_printer.get_temperature)
        log.debug("PRINTER_STATUS  pos=%s  hotend=%s  bed=%s",
                  pos.as_dict(), temp.get("hotend_temp"), temp.get("bed_temp"))
        return {
            "position":     pos.as_dict(),
            "temperatures": {
                "hotend_temp": temp["hotend_temp"],
                "bed_temp":    temp["bed_temp"],
            },
        }

    raise ValueError(f"Unknown action: '{action}'")


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    """
    Single persistent WebSocket per PC client.

    Inbound:  { "id": "<uuid>", "action": "<action>", "params": { ... } }
    Success:  { "id": "<uuid>", "status": "ok",    "data": { ... } }
    Error:    { "id": "<uuid>", "status": "error",  "detail": "...", "code": <int> }

    Limit exceeded (status "ok", check data.moved):
              { "id": "...", "status": "ok",
                "data": { "moved": false, "warning": "Move rejected: ..." } }
    """
    await websocket.accept()
    log.info("WS CLIENT CONNECTED  remote=%s", websocket.client)

    try:
        while True:
            raw_msg = await websocket.receive_text()
            log.debug("WS RECV  %s", raw_msg[:300])

            # ── Parse ────────────────────────────────────────────────────
            try:
                msg    = json.loads(raw_msg)
                action = msg.get("action", "")
                params = msg.get("params") or {}
                msg_id = msg.get("id", "")
            except json.JSONDecodeError as exc:
                log.error("JSON PARSE ERROR  %s", exc)
                await websocket.send_text(json.dumps({
                    "id": None, "status": "error",
                    "detail": f"Invalid JSON: {exc}", "code": 400,
                }))
                continue

            # ── Dispatch ─────────────────────────────────────────────────
            try:
                data  = await _dispatch(action, params)
                reply = json.dumps({"id": msg_id, "status": "ok", "data": data})
                log.debug("WS SEND  %s", reply[:300])
                await websocket.send_text(reply)

            except PrinterNotConnectedError as exc:
                log.error("NOT CONNECTED  %s", exc)
                await websocket.send_text(json.dumps({
                    "id": msg_id, "status": "error",
                    "detail": str(exc), "code": 503,
                }))
            except PrinterTimeoutError as exc:
                log.error("PRINTER TIMEOUT  %s", exc)
                await websocket.send_text(json.dumps({
                    "id": msg_id, "status": "error",
                    "detail": str(exc), "code": 504,
                }))
            except (ValueError, KeyError) as exc:
                log.error("BAD PARAMS  %s", exc)
                await websocket.send_text(json.dumps({
                    "id": msg_id, "status": "error",
                    "detail": str(exc), "code": 422,
                }))
            except Exception as exc:
                log.exception("UNEXPECTED ERROR  action=%s", action)
                await websocket.send_text(json.dumps({
                    "id": msg_id, "status": "error",
                    "detail": str(exc), "code": 500,
                }))

    except WebSocketDisconnect:
        log.info("WS CLIENT DISCONNECTED  remote=%s", websocket.client)
    except Exception as exc:
        log.exception("WS ENDPOINT CRASHED  %s", exc)
