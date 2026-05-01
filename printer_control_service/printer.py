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

    def home(self, axes: Optional[list[str]] = None) -> None:
        """
        Home axes.  Pass None or an empty list to home all axes.
        Pass e.g. ['X', 'Z'] to home specific axes.
        """
        axes_str = " ".join(a.upper() for a in axes) if axes else ""
        cmd = f"G28 {axes_str}".strip()
        logger.info("home: %s", cmd)
        with self._lock:
            self._require_connected()
            self._send_locked(cmd, timeout=120)

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
