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
    port: str = "/dev/ttyACM0"
    baud_rate: int = 230400
    timeout: float = 5.0
    # Feed rates (mm/min)
    feed_xy: int = 3000
    feed_z: int = 1000
    feed_e: int = 300


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
        """Open the serial port and initialise absolute positioning mode."""
        with self._lock:
            if self._ser and self._ser.is_open:
                logger.info(
                    "connect() called but already open on %s @ %d baud",
                    self.config.port, self.config.baud_rate,
                )
                return  # already connected

            logger.info(
                "Opening serial port %s @ %d baud (timeout=%.1fs)",
                self.config.port, self.config.baud_rate, self.config.timeout,
            )
            self._ser = serial.Serial(
                self.config.port,
                self.config.baud_rate,
                timeout=self.config.timeout,
            )
            logger.debug("Waiting 2 s for Marlin greeting banner…")
            time.sleep(2)                   # wait for Marlin greeting banner
            self._ser.reset_input_buffer()
            logger.debug("Input buffer flushed after greeting")
            self._send_locked("G90")        # absolute mode
            logger.info(
                "Serial port open and printer in absolute mode (%s)",
                self.config.port,
            )

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
        Home X axis by jogging in the -X direction, step_mm at a time, until
        the GPIO limit switch (X_MIN, BCM pin 4) is triggered (pin pulled
        LOW / grounded).

        Does NOT send G28 — homing is done entirely via GPIO feedback.

        Sequence per step:
            1. Send G1 X-<step_mm> F600  (relative jog toward home end)
            2. Send M400                 (block until motor physically stops)
            3. Read GPIO — if X_MIN is LOW (triggered), stop immediately.

        M400 is critical: Marlin's 'ok' for G1 only means the command was
        enqueued, not that the motor stopped.  Without M400 the planner buffer
        fills with several steps ahead, and the motor keeps running for
        multiple steps after GPIO triggers.

        *axes* is accepted for API compatibility but only X is homed.

        Returns a dict with homing result details.
        Raises RuntimeError if the switch is never triggered within max_steps.
        """
        import gpio_manager

        switch_name  = "X_MIN"   # GPIO name defined in gpio_manager.LIMIT_SWITCH_PINS
        step_mm      = 1.0        # jog distance per iteration (mm)
        homing_feed  = 600        # slow feed rate for safe approach (mm/min)
        max_steps    = 300        # safety cutoff (~300 mm max travel at 1 mm/step)

        if axes:
            requested = [a.upper() for a in axes]
            if "X" not in requested:
                logger.warning(
                    "home: only X limit-switch homing is supported; ignoring axes=%s",
                    requested,
                )

        logger.info(
            "home: limit-switch seek on +X  step=%.1f mm  feed=%d mm/min  switch=%s",
            step_mm, homing_feed, switch_name,
        )

        with self._lock:
            self._require_connected()

            # Already seated on the switch — nothing to move.
            if gpio_manager.is_triggered(switch_name):
                logger.info("home: %s already triggered — X already at home", switch_name)
                return {
                    "method":            "limit_switch",
                    "switch":            switch_name,
                    "reached_switch":    True,
                    "steps":             0,
                    "distance_mm":       0.0,
                    "already_at_switch": True,
                }

            if not gpio_manager.gpio_available():
                raise RuntimeError(
                    "GPIO not available — cannot home via limit switch. "
                    "Check RPi.GPIO wiring on the Pi."
                )

            self._ser.reset_input_buffer()
            self._send_locked("G91")   # relative mode for repeated jogs

            steps_taken = 0
            for _ in range(max_steps):
                # Jog one step toward the limit switch.
                self._send_locked(f"G1 X-{step_mm:g} F{homing_feed}")

                # M400 blocks until the planner queue is drained and the motor
                # has physically stopped.  Without this, Marlin's 'ok' for G1
                # only means the command was enqueued — the buffer can hold
                # many moves ahead, so GPIO would be checked while several
                # queued steps are still executing, causing the late stop.
                self._send_locked("M400")
                steps_taken += 1

                # Check limit switch after the move is physically complete.
                # Pin LOW (grounded) = switch triggered = stop.
                if gpio_manager.is_triggered(switch_name):
                    logger.info(
                        "home: %s triggered after %d step(s) (%.1f mm)",
                        switch_name, steps_taken, steps_taken * step_mm,
                    )
                    break

            # No residual motion remains — M400 was already issued per step.
            self._send_locked("G90")   # restore absolute positioning

            if not gpio_manager.is_triggered(switch_name):
                raise RuntimeError(
                    f"Homing failed: {switch_name} not triggered after "
                    f"{steps_taken} step(s) of {step_mm} mm on +X axis. "
                    f"Check wiring or increase max_steps."
                )

            return {
                "method":            "limit_switch",
                "switch":            switch_name,
                "reached_switch":    True,
                "steps":             steps_taken,
                "distance_mm":       round(steps_taken * step_mm, 3),
                "already_at_switch": False,
            }

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