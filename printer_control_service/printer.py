"""
printer.py — low-level serial interface to a Marlin-based 3D printer.

This module is intentionally framework-agnostic: no FastAPI, no CLI.
It is imported by main.py (FastAPI) or can be used from any other context.
"""

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import serial

# ---------------------------------------------------------------------------
# Logger — set to DEBUG to see every byte exchanged with the printer.
# In production you can raise this to INFO to silence the serial chatter.
# ---------------------------------------------------------------------------

logger = logging.getLogger("printer_pi.serial")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class PrinterNotConnectedError(RuntimeError):
    """Raised when a command is issued but the serial port is not open."""


class PrinterTimeoutError(RuntimeError):
    """Raised when the printer does not reply 'ok' within the deadline."""


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class PrinterConfig:
    # Preferred port; connect() falls back through the others because the
    # Pi renumbers /dev/ttyACM* on reboot or replug.
    port: str = "/dev/ttyACM2"
    fallback_ports: tuple[str, ...] = ("/dev/ttyACM0", "/dev/ttyACM1", "/dev/ttyACM2")
    baud_rate: int = 230400
    timeout: float = 5.0
    # Feed rates (mm/min)
    feed_xy: int = 3000
    feed_z: int = 1000
    feed_e: int = 300
    # M92 on this machine reports X100 Y100 — needed to convert the raw
    # CoreXY A/B stepper counts in M114 back into real millimetres.
    steps_per_mm_xy: float = 100.0


@dataclass
class Position:
    X: float = 0.0
    Y: float = 0.0
    Z: float = 0.0
    E: float = 0.0

    def as_dict(self) -> dict:
        return {"X": self.X, "Y": self.Y, "Z": self.Z, "E": self.E}


# ---------------------------------------------------------------------------
# Printer class
# ---------------------------------------------------------------------------

class Printer:
    """
    Thread-safe wrapper around a Marlin serial connection.

    Usage
    -----
    p = Printer(PrinterConfig(port="/dev/ttyACM0"))
    p.connect()
    p.move("X", 10.0)
    pos = p.get_position()
    p.disconnect()
    """

    def __init__(self, config: Optional[PrinterConfig] = None):
        self.config: PrinterConfig = config or PrinterConfig()
        self._ser: Optional[serial.Serial] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """
        Open the serial port and initialise absolute positioning mode.

        Tries config.port first, then config.fallback_ports. A port only
        counts as the printer if it answers M115 like Marlin, so another
        ACM device is not silently adopted.

        NOTE: no M211 S0 here. On Buddy 6.4.0 the travel clamp that bites
        us is position_is_reachable(), which tests the raw compile-time
        X/Y_MIN_POS..MAX_POS macros and is NOT controlled by M211 — so
        disabling soft endstops changes nothing. See home() for details.
        """
        with self._lock:
            if self._ser and self._ser.is_open:
                logger.info(
                    "connect() called but already open on %s @ %d baud",
                    self.config.port, self.config.baud_rate,
                )
                return  # already connected

            candidates: list[str] = [self.config.port]
            for p in self.config.fallback_ports:
                if p not in candidates:
                    candidates.append(p)

            logger.info("Scanning for printer on %s", ", ".join(candidates))

            errors: list[str] = []
            for port in candidates:
                ser = None
                try:
                    logger.info("Trying %s …", port)
                    ser = serial.Serial(
                        port, self.config.baud_rate, timeout=self.config.timeout,
                    )
                    time.sleep(2)           # wait for Marlin greeting banner
                    ser.reset_input_buffer()

                    if not self._probe_marlin(ser):
                        logger.info("  %s opened but did not identify as Marlin", port)
                        errors.append(f"{port}: no M115 response")
                        ser.close()
                        continue

                    self._ser = ser
                    self.config.port = port
                    self._send_locked("G90")        # absolute mode
                    logger.info("Serial port open, absolute mode (%s)", port)
                    return

                except (serial.SerialException, OSError) as exc:
                    logger.info("  %s unavailable: %s", port, exc)
                    errors.append(f"{port}: {exc}")
                    if ser is not None:
                        try:
                            ser.close()
                        except Exception:
                            pass

            self._ser = None
            raise PrinterNotConnectedError(
                "No printer found on any candidate port. Tried:\n  "
                + "\n  ".join(errors)
            )

    def _probe_marlin(self, ser: serial.Serial) -> bool:
        """
        Send M115 on *ser* and report whether it answers like Marlin.

        Writes to the passed handle directly rather than via _send_locked,
        which requires self._ser to already be assigned — that is exactly
        what this call is still deciding.
        """
        try:
            ser.reset_input_buffer()
            ser.write(b"M115\n")
            deadline = time.time() + 3.0
            while time.time() < deadline:
                raw = ser.readline().decode(errors="ignore").strip()
                if not raw:
                    continue
                logger.debug("RX  %s", raw)
                if "FIRMWARE_NAME" in raw:
                    logger.info("  identified: %s", raw[:80])
                    return True
                if raw.startswith("ok"):
                    return True
            return False
        except Exception as exc:
            logger.debug("probe failed on %s: %s", ser.port, exc)
            return False

    def disconnect(self) -> None:
        """Close the serial port gracefully."""
        with self._lock:
            if self._ser and self._ser.is_open:
                self._ser.close()
                logger.info("Serial port %s closed", self.config.port)
            self._ser = None

    @property
    def is_connected(self) -> bool:
        return self._ser is not None and self._ser.is_open

    # ------------------------------------------------------------------
    # Public commands
    # ------------------------------------------------------------------

    def send_gcode(self, cmd: str, timeout: Optional[float] = None) -> list[str]:
        """
        Send a raw G-code command and collect all response lines until 'ok'.

        Returns the list of response lines (including the 'ok' line).
        Raises PrinterTimeoutError if 'ok' is not received in time.
        """
        with self._lock:
            self._ser.reset_input_buffer()   # clear unsolicited reports before raw command
            return self._send_locked(cmd, timeout=timeout)

    def get_position(self) -> Position:
        """Query the printer with M114 and return a Position dataclass."""
        with self._lock:
            self._require_connected()
            self._ser.reset_input_buffer()
            self._ser.write(b"M114\n")
            logger.debug("TX  M114")
            deadline = time.time() + self.config.timeout
            while time.time() < deadline:
                line = self._ser.readline().decode(errors="ignore").strip()
                if line:
                    logger.debug("RX  %s", line)
                parsed = {}
                for axis in ("X", "Y", "Z", "E"):
                    m = re.search(rf"{axis}:(-?\d+\.\d+)", line)
                    if m:
                        parsed[axis] = float(m.group(1))
                if parsed:
                    return Position(**{k: parsed.get(k, 0.0) for k in ("X", "Y", "Z", "E")})
        raise PrinterTimeoutError("M114 did not return position data in time")

    def get_true_xy(self) -> tuple[float, float]:
        """
        Return the REAL (x_mm, y_mm) derived from the raw stepper counts.

        Why this exists
        ---------------
        M114's X:/Y:/Z: fields cannot be trusted on this firmware. In
        Buddy 6.4.0 prepare_move_to_destination() ends with:

            prepare_move_to(destination, feedrate_mm_s, hints);
            current_position = destination;     // unconditional

        current_position is assigned even when prepare_move_to() bailed
        out early because the target was unreachable. So a rejected move
        still advances the reported position — that is how M114 came to
        report Y:-319 while the head was physically sitting at -19.

        The 'Count A:.. B:..' fields are the actual stepper positions and
        do not lie. This is a CoreXY machine, so A/B are motor positions,
        not axes; the firmware's own transform (homing_corexy.cpp) is:

            x = (a + b) / 2
            y = (a - b) / 2

        divided by steps-per-mm.

        Raises PrinterTimeoutError if no Count fields arrive in time.
        """
        with self._lock:
            self._require_connected()
            return self._true_xy_locked()

    def _true_xy_locked(self) -> tuple[float, float]:
        """get_true_xy() body; caller must already hold self._lock."""
        self._ser.reset_input_buffer()
        self._ser.write(b"M114\n")
        logger.debug("TX  M114  (stepper counts)")

        deadline = time.time() + self.config.timeout
        while time.time() < deadline:
            line = self._ser.readline().decode(errors="ignore").strip()
            if not line:
                continue
            logger.debug("RX  %s", line)
            m = re.search(r"Count\s+A:(-?\d+)\s+B:(-?\d+)", line)
            if m:
                a, b = int(m.group(1)), int(m.group(2))
                spm = self.config.steps_per_mm_xy
                return ((a + b) / 2.0 / spm, (a - b) / 2.0 / spm)
        raise PrinterTimeoutError("M114 did not report stepper counts in time")

    def get_temperature(self) -> dict:
        """
        Query hotend and bed temperatures with M105.

        Returns a dict::

            {
                "hotend_temp": 215.3,   # T:  — None if not reported
                "bed_temp":     60.0,   # B:  — None if not reported
                "raw":         "ok T:215.3 /215.0 B:60.0 /60.0 ...",
            }

        Raises PrinterTimeoutError if no temperature line arrives in time.
        """
        with self._lock:
            self._require_connected()
            self._ser.reset_input_buffer()
            self._ser.write(b"M105\n")
            logger.debug("TX  M105")
            deadline = time.time() + self.config.timeout
            while time.time() < deadline:
                raw = self._ser.readline().decode(errors="ignore").strip()
                if not raw:
                    continue
                logger.debug("RX  %s", raw)
                # Marlin responds with a line containing T: and/or B:
                hotend_m = re.search(r"\bT:([\d.]+)", raw)
                bed_m    = re.search(r"\bB:([\d.]+)", raw)
                if hotend_m or bed_m:
                    return {
                        "hotend_temp": float(hotend_m.group(1)) if hotend_m else None,
                        "bed_temp":    float(bed_m.group(1))    if bed_m    else None,
                        "raw":         raw,
                    }
        raise PrinterTimeoutError("M105 did not return temperature data in time")

    def move(self, axis: str, distance: float, feed: Optional[int] = None) -> None:
        """
        Move a single axis by *distance* mm in relative mode, then restore
        absolute positioning.

        axis     : one of X / Y / Z / E  (case-insensitive)
        distance : signed millimetres
        feed     : mm/min override; falls back to per-axis default from config
        """
        axis = axis.upper()
        if axis not in ("X", "Y", "Z", "E"):
            raise ValueError(f"Unknown axis '{axis}'. Must be X, Y, Z or E.")

        if feed is None:
            feed = self._default_feed(axis)

        logger.info(
            "move: axis=%s  distance=%+g mm  feed=%d mm/min", axis, distance, feed
        )

        with self._lock:
            self._require_connected()
            # Flush once before the sequence to clear any unsolicited Marlin
            # reports (e.g. temperature auto-reports) that arrived since the
            # last command.  Must NOT be repeated between commands — see
            # _send_locked docstring.
            self._ser.reset_input_buffer()
            self._send_locked("G91")                          # relative mode
            self._send_locked(f"G1 {axis}{distance:+g} F{feed}")
            self._send_locked("M400")                         # wait for moves
            self._send_locked("G90")                          # absolute mode

        logger.info("move: axis=%s complete", axis)

    def home(self, axes: Optional[list[str]] = None) -> dict:
        """
        Home X, Y, then Z by jogging toward each GPIO limit switch until
        the pin is pulled LOW (triggered).

        Does NOT send G28 — homing is done entirely via GPIO feedback.

        Default order (always X → Y → Z when axes is None / full home):
            X_MIN (BCM 27)  seek G1 X+0.5, backoff X-
            Y_MIN (BCM 17)  seek G1 Y+0.5, backoff Y-
            Z_MIN (BCM 4)   seek G1 Z-0.5, backoff Z+

        Per-axis sequence:
            0. If already on the switch, back off until it releases (so X
               always moves first even when seated on X_MIN)
            1. Send G1 <axis><dir><step_mm> F600 toward the switch
            2. Send M400 (block until motor physically stops)
            3. Read GPIO — if switch is LOW (triggered), stop immediately
            4. Back off opposite direction so the switch opens again

        M400 is critical: Marlin's 'ok' for G1 only means the command was
        enqueued, not that the motor stopped.

        *axes* may restrict which axes to home (e.g. ["X"]). Order among
        requested axes still follows X → Y → Z.

        Returns a dict with per-axis homing results.
        Raises RuntimeError if any switch is never triggered within max_steps.
        """
        import gpio_manager

        # Per-axis seek config: switch name, seek sign (+1 / -1), step, backoff
        # Seek sign is the firmware G1 direction toward the limit switch.
        #
        # SEEK DIRECTION IS NOT FREE TO CHOOSE. Buddy boots every axis at
        # one END of its travel window (motion.cpp:131, current_position =
        # {X_HOME_POS, Y_HOME_POS, Z_HOME_POS}) regardless of where the head
        # physically is, and position_is_reachable() then silently drops any
        # move that would leave the window:
        #
        #   X  boots 252 (X_MAX_POS)  = the RIGHT end
        #   Y  boots -19 (Y_MIN_POS)  = the FRONT end
        #   Z  boots   0 (Z_MIN_POS)
        #
        # The switches sit at exactly those ends, and park() leaves the head
        # ON them before power-off. So at the next boot the head is already
        # at the switch and homing never has to seek toward it — which it
        # could not do anyway, since the firmware believes it is standing
        # there and refuses any move further that way.
        #
        # Every move homing does make IS legal:
        #   - backing off a pressed switch goes AWAY from the boot end, which
        #     is the direction with the whole window of room available
        #   - the re-approach then seeks back within the room just created
        #
        # Seeking toward a switch from an arbitrary position only works when
        # headroom already exists, i.e. once the head has moved away from the
        # boot end. That is the end-of-session case, which is what park()
        # does. If power is lost mid-session the head will be stranded away
        # from the switches; push it to the right-front corner by hand before
        # powering on. The headroom probe below catches that case.
        axis_home_cfg: dict[str, dict] = {
            "X": {
                "switch": "X_MIN",
                "seek_sign": +1,   # G1 X+0.5 -> RIGHT, switch on the right
                "step_mm": 0.5,
                "backoff_mm": 1.0,
            },
            "Y": {
                "switch": "Y_MIN",
                "seek_sign": -1,   # G1 Y-0.5 -> FRONT, switch at the front
                "step_mm": 0.5,
                "backoff_mm": 1.0,
            },
            "Z": {
                "switch": "Z_MIN",
                "seek_sign": -1,   # toward Z_MIN, the boot end
                "step_mm": 0.5,
                "backoff_mm": 1.0,
            },
        }
        # Fixed home order regardless of caller request list
        home_order = ("X", "Y", "Z")
        # Slow feed rate for safe approach (mm/min)
        homing_feed = 600
        # Safety cutoff (~300 mm max travel at 0.5 mm/step)
        max_steps = 600
        # Max steps while backing off a switch that was already pressed
        max_backoff_steps = 40

        if axes:
            requested = {a.upper() for a in axes}
            unknown = requested - set(home_order)
            if unknown:
                logger.warning("home: ignoring unknown axes=%s", sorted(unknown))
            to_home = [ax for ax in home_order if ax in requested]
            if not to_home:
                raise RuntimeError(
                    f"No supported axes to home from request={list(axes)}; "
                    f"supported={list(home_order)}"
                )
        else:
            to_home = list(home_order)

        logger.info(
            "home: limit-switch sequence %s  feed=%d mm/min",
            " → ".join(to_home), homing_feed,
        )

        with self._lock:
            self._require_connected()

            if not gpio_manager.gpio_available():
                raise RuntimeError(
                    "GPIO not available — cannot home via limit switch. "
                    "Check RPi.GPIO wiring on the Pi."
                )

            self._ser.reset_input_buffer()
            self._send_locked("G91")   # relative mode for repeated jogs

            # Collect per-axis outcome for the API response
            results: dict[str, dict] = {}

            try:
                for axis in to_home:
                    cfg = axis_home_cfg[axis]
                    switch_name = cfg["switch"]
                    step_mm = float(cfg["step_mm"])
                    backoff_mm = float(cfg["backoff_mm"])
                    seek_sign = int(cfg["seek_sign"])
                    # Opposite of seek — used to leave the switch
                    backoff_sign = -seek_sign
                    seek_delta = seek_sign * step_mm
                    backoff_delta = backoff_sign * backoff_mm

                    logger.info(
                        "========== HOMING AXIS %s  switch=%s  seek=%+.1f ==========",
                        axis, switch_name, seek_delta,
                    )

                    # True when already seated on the switch before this axis starts
                    already_at_switch = gpio_manager.is_triggered(switch_name)

                    # ---- Headroom probe (only when NOT on the switch) ---
                    # At every cold boot Buddy initialises position to the
                    # BOTTOM of its travel window:
                    #
                    #   motion.cpp:131
                    #   xyze_pos_t current_position =
                    #       { X_HOME_POS, Y_HOME_POS, Z_HOME_POS };
                    #
                    # which for min-homed axes resolve to X_MIN_POS (-2)
                    # and Y_MIN_POS (-19) — wherever the head physically
                    # is. Our switches sit at that same minimum end, so a
                    # seek is negative and the firmware has ZERO room to
                    # give: every step is silently dropped by
                    # position_is_reachable() while M114 counts down
                    # anyway. One step checked against the STEPPER COUNTS
                    # turns that silent no-op into a clear error.
                    #
                    # This only applies when the head is NOT already on
                    # the switch. Starting ON the switch is the CORRECT
                    # state: there the first move is a positive backoff,
                    # which always has headroom, so probing negatively
                    # here would fail a perfectly good setup.
                    if not already_at_switch and axis in ("X", "Y"):
                        idx = 0 if axis == "X" else 1
                        probe_before = self._true_xy_locked()
                        self._send_locked(
                            f"G1 {axis}{seek_delta:+g} F{homing_feed}"
                        )
                        self._send_locked("M400")
                        probe_after = self._true_xy_locked()

                        moved = abs(probe_after[idx] - probe_before[idx])
                        logger.info(
                            "home: %s headroom probe moved %.3f mm (want ~%.2f)",
                            axis, moved, step_mm,
                        )
                        if moved < step_mm * 0.5:
                            raise RuntimeError(
                                f"Homing blocked on {axis}: commanded "
                                f"{seek_delta:+g} mm but the steppers moved only "
                                f"{moved:.3f} mm — the firmware accepted the "
                                f"command and refused the motion.\n"
                                f"The head is not on {switch_name}, and {axis} "
                                f"boots pinned against the very end the switch "
                                f"sits at — so the firmware believes it is "
                                f"already there and refuses to travel further "
                                f"that way. Homing cannot seek from here.\n"
                                f"This means the last session did not finish "
                                f"with park() (power loss, or the head was "
                                f"moved while off).\n"
                                f"Fix: power OFF, push the head into the "
                                f"RIGHT-FRONT corner by hand until the switches "
                                f"click, then power on and home again. Calling "
                                f"park() before every shutdown avoids this."
                            )

                    # If already on the switch, move away until it releases so the
                    # following seek is a full approach (X is never "invisible").
                    if already_at_switch:
                        logger.info(
                            "home: %s already TRIGGERED — backing off until released "
                            "before seek",
                            switch_name,
                        )
                        released = False
                        for _ in range(max_backoff_steps):
                            self._send_locked(
                                f"G1 {axis}{backoff_delta:+g} F{homing_feed}"
                            )
                            self._send_locked("M400")
                            if not gpio_manager.is_triggered(switch_name):
                                released = True
                                logger.info(
                                    "home: %s released — starting seek on %s",
                                    switch_name, axis,
                                )
                                break
                        if not released:
                            raise RuntimeError(
                                f"Homing failed: {switch_name} stayed triggered after "
                                f"{max_backoff_steps} backoff step(s) on {axis}. "
                                f"Check wiring / stuck switch."
                            )

                    steps_taken = 0
                    for _ in range(max_steps):
                        # Jog one step toward the limit switch.
                        self._send_locked(
                            f"G1 {axis}{seek_delta:+g} F{homing_feed}"
                        )
                        # M400 waits until the motor has physically stopped.
                        self._send_locked("M400")
                        steps_taken += 1

                        if gpio_manager.is_triggered(switch_name):
                            logger.info(
                                "home: %s triggered after %d step(s) (%.1f mm)",
                                switch_name, steps_taken, steps_taken * step_mm,
                            )
                            break

                    if not gpio_manager.is_triggered(switch_name):
                        raise RuntimeError(
                            f"Homing failed: {switch_name} not triggered after "
                            f"{steps_taken} step(s) of {step_mm} mm on "
                            f"{axis}{'+' if seek_sign > 0 else '-'} axis. "
                            f"Check wiring or increase max_steps."
                        )

                    # Final retract so the pin is no longer grounded.
                    logger.info(
                        "home: final backoff %+.1f mm on %s to release %s",
                        backoff_delta, axis, switch_name,
                    )
                    self._send_locked(
                        f"G1 {axis}{backoff_delta:+g} F{homing_feed}"
                    )
                    self._send_locked("M400")

                    switch_released = not gpio_manager.is_triggered(switch_name)
                    if not switch_released:
                        logger.warning(
                            "home: %s still grounded after %.1f mm backoff",
                            switch_name, backoff_mm,
                        )

                    logger.info("========== AXIS %s DONE ==========", axis)

                    results[axis] = {
                        "switch":            switch_name,
                        "reached_switch":    True,
                        "steps":             steps_taken,
                        "distance_mm":       round(steps_taken * step_mm, 3),
                        "seek_delta_mm":     seek_delta,
                        "backoff_mm":        backoff_mm,
                        "switch_released":   switch_released,
                        "already_at_switch": already_at_switch,
                    }
            finally:
                # Always restore absolute mode even if an axis fails mid-sequence
                self._send_locked("G90")

            return {
                "method":  "limit_switch",
                "axes":    to_home,
                "results": results,
            }

    def park(self, max_travel_mm: float = 300.0) -> dict:
        """
        Drive X and Y onto their limit switches and LEAVE the head there.
        Call this at the end of every session, before powering down.

        This is the operation the whole setup depends on.

        Buddy assigns current_position = {X_HOME_POS, Y_HOME_POS, Z_HOME_POS}
        at every cold boot — for this machine X_MAX_POS (252, right) and
        Y_MIN_POS (-19, front) — no matter where the head really is. Nothing
        over serial can correct that afterwards: G92 only shifts the workspace
        offset (G92.cpp does `position_shift[i] += d` for X/Y/Z and leaves
        native position alone), and the clamp that enforces travel reads the
        raw compile-time macros. Homing state does not survive either; it
        lives in RAM and is gone at power-off.

        So the ONLY thing that carries across a power cycle is where the head
        physically is. Parking it on the switches — which sit at exactly the
        coordinates the firmware will assume — makes that assumption true, and
        does it to switch precision rather than however hard someone pushed the
        head into a corner by hand.

        Unlike home(), this does NOT back off at the end. The head is meant to
        stay pressed on the switches so the next boot starts there.

        Seeking here is legal because by now the head has moved away from the
        boot end during the session, so headroom toward the switches exists.
        That is not true at boot, which is why home() cannot seek and park()
        can.
        """
        import gpio_manager

        # Same ends the firmware boots at: X -> right (X_MAX), Y -> front (Y_MIN)
        park_cfg = (("X", "X_MIN", +1), ("Y", "Y_MIN", -1))
        park_feed = 1500
        step_mm = 1.0

        logger.info("park: seeking limit switches to set up the next boot")

        with self._lock:
            self._require_connected()

            if not gpio_manager.gpio_available():
                raise RuntimeError(
                    "GPIO not available — cannot park without limit switches."
                )

            self._ser.reset_input_buffer()
            self._send_locked("G91")   # relative
            results: dict[str, dict] = {}

            try:
                for axis, switch_name, seek_sign in park_cfg:
                    idx = 0 if axis == "X" else 1
                    delta = seek_sign * step_mm

                    if gpio_manager.is_triggered(switch_name):
                        logger.info(
                            "park: %s already resting on %s", axis, switch_name
                        )
                        results[axis] = {"switch": switch_name,
                                         "already_parked": True,
                                         "reached_switch": True,
                                         "travelled_mm": 0.0}
                        continue

                    start = self._true_xy_locked()
                    reached = False

                    for _ in range(int(max_travel_mm / step_mm)):
                        self._send_locked(f"G1 {axis}{delta:+g} F{park_feed}")
                        self._send_locked("M400")
                        if gpio_manager.is_triggered(switch_name):
                            reached = True
                            break

                    end = self._true_xy_locked()
                    travelled = abs(end[idx] - start[idx])

                    if reached:
                        logger.info(
                            "park: %s parked on %s after %.1f mm",
                            axis, switch_name, travelled,
                        )
                    else:
                        logger.warning(
                            "park: %s never reached %s — only %.1f mm of real "
                            "travel. The next boot will NOT be aligned.",
                            axis, switch_name, travelled,
                        )

                    results[axis] = {"switch": switch_name,
                                     "already_parked": False,
                                     "reached_switch": reached,
                                     "travelled_mm": round(travelled, 2)}
            finally:
                self._send_locked("G90")   # restore absolute

        parked = all(r["reached_switch"] for r in results.values())
        logger.info("park: complete  parked=%s", parked)
        if not parked:
            logger.warning(
                "park: INCOMPLETE — push the head into the right-front corner "
                "by hand before powering on, or the next session cannot home."
            )
        return {"parked": parked, "results": results}

    def emergency_stop(self) -> None:
        """Send M112 (firmware emergency stop — requires printer reset)."""
        logger.warning("EMERGENCY STOP (M112) sent!")
        with self._lock:
            self._require_connected()
            self._ser.write(b"M112\n")

    # ------------------------------------------------------------------
    # Private helpers (must be called while holding self._lock)
    # ------------------------------------------------------------------

    def _require_connected(self) -> None:
        if not (self._ser and self._ser.is_open):
            raise PrinterNotConnectedError("Printer is not connected")

    def _send_locked(self, cmd: str, timeout: Optional[float] = None) -> list[str]:
        """
        Send a G-code command and block until 'ok' is received.

        Do NOT flush the input buffer here — this helper is called multiple
        times per public method (G91 → G1 → M400 → G90 in move()).  Flushing
        between commands in a sequence discards the 'ok' for the previous
        command (or for M400 when a fast move finishes before M400 is sent),
        which causes G90 to be sent before the move completes, aborting it.

        Callers that need a clean slate (move, send_gcode) flush the buffer
        once at their own entry point before calling _send_locked.
        """
        self._require_connected()
        timeout = timeout if timeout is not None else self.config.timeout

        self._ser.write((cmd.strip() + "\n").encode())
        logger.debug("TX  %s", cmd.strip())

        lines: list[str] = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = self._ser.readline().decode(errors="ignore").strip()
            if raw:
                lines.append(raw)
                logger.debug("RX  %s", raw)
            if raw.startswith("ok"):
                return lines

        raise PrinterTimeoutError(
            f"No 'ok' received for '{cmd}' within {timeout}s. "
            f"Responses so far: {lines}"
        )

    def _default_feed(self, axis: str) -> int:
        mapping = {
            "X": self.config.feed_xy,
            "Y": self.config.feed_xy,
            "Z": self.config.feed_z,
            "E": self.config.feed_e,
        }
        return mapping[axis]