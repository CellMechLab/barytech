"""
gpio_manager.py — Raspberry Pi GPIO manager for limit switches.

Uses RPi.GPIO directly (no gpiozero dependency).

Wiring convention:
    Each limit switch is wired between a BCM GPIO pin and GND.
    The internal pull-up resistor is enabled, so:
        Pin HIGH (1) = switch open   (not triggered)
        Pin LOW  (0) = switch closed (triggered)

Pin assignment (BCM numbering) — edit to match your wiring:
    Z_MIN → GPIO 4
    Y_MIN → GPIO 27   (uncomment when wired)
    X_MIN → GPIO 17  (uncomment when wired)

A background monitor polls pins and logs whenever a switch is pressed
or released so you can verify wiring without running a home cycle.
"""

import logging
import threading
import time

log = logging.getLogger("gpio")

# ---------------------------------------------------------------------------
# Pin map  —  BCM GPIO pin numbers, edit to match your physical wiring.
# Comment out any axis whose switch is not yet physically wired.
# ---------------------------------------------------------------------------

LIMIT_SWITCH_PINS: dict[str, int] = {
    "Z_MIN": 4,
    # "Y_MIN": 27,
    # "X_MIN": 17,
}

# How often the background monitor samples pin state (seconds)
_MONITOR_POLL_S: float = 0.05

# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------

# True after RPi.GPIO setup succeeds
_gpio_available: bool = False

# Last known triggered state per switch — used for edge-detect logging
_last_states: dict[str, bool] = {}

# Background thread that watches for press/release edges
_monitor_thread: threading.Thread | None = None

# Set when cleanup is requested so the monitor loop exits
_monitor_stop: threading.Event = threading.Event()


# ---------------------------------------------------------------------------
# Init / cleanup
# ---------------------------------------------------------------------------

def init_gpio() -> None:
    """
    Initialise all limit-switch GPIO pins using RPi.GPIO directly.
    Safe to call when no pins are configured — skips silently.
    Starts a background monitor that logs press/release events.
    """
    global _gpio_available

    if not LIMIT_SWITCH_PINS:
        log.info("GPIO INIT  no pins configured — skipping")
        _gpio_available = False
        return

    try:
        import RPi.GPIO as GPIO  # type: ignore
        GPIO.setwarnings(False)
        GPIO.cleanup()                          # release any stale pin state
        GPIO.setmode(GPIO.BCM)
        for name, pin in LIMIT_SWITCH_PINS.items():
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            # Snapshot initial level so the first poll does not fake an edge
            triggered = GPIO.input(pin) == GPIO.LOW
            _last_states[name] = triggered
            log.info(
                "GPIO INIT  %s → BCM pin %d  initial=%s",
                name, pin, "TRIGGERED" if triggered else "open",
            )
        _gpio_available = True
        log.info("GPIO ready — %d limit switches registered", len(LIMIT_SWITCH_PINS))
        _start_monitor()

    except (ImportError, Exception) as exc:
        # ImportError on non-Pi hosts; other errors if pins are busy / permissions
        log.warning(
            "GPIO init failed (%s). Running without GPIO "
            "(all switches report 'open').",
            exc,
        )
        _gpio_available = False


def cleanup_gpio() -> None:
    """Stop the monitor thread and release all GPIO resources."""
    _stop_monitor()
    if not _gpio_available:
        return
    try:
        import RPi.GPIO as GPIO  # type: ignore
        GPIO.cleanup()
        log.info("GPIO cleanup complete")
    except Exception as exc:
        # Avoid crashing shutdown if the library is already torn down
        log.warning("GPIO cleanup error: %s", exc)


# ---------------------------------------------------------------------------
# Background edge monitor — logs when a switch is pressed or released
# ---------------------------------------------------------------------------

def _start_monitor() -> None:
    """Spawn a daemon thread that polls pins and logs state changes."""
    global _monitor_thread
    _stop_monitor()
    _monitor_stop.clear()
    # Daemon so the process can exit even if the thread is mid-sleep
    _monitor_thread = threading.Thread(
        target=_monitor_loop,
        name="gpio-limit-monitor",
        daemon=True,
    )
    _monitor_thread.start()
    log.info(
        "GPIO monitor started — press a limit switch to see TRIGGERED / RELEASED logs"
    )


def _stop_monitor() -> None:
    """Signal the monitor thread to exit and wait briefly for it."""
    global _monitor_thread
    _monitor_stop.set()
    if _monitor_thread is not None and _monitor_thread.is_alive():
        _monitor_thread.join(timeout=1.0)
    _monitor_thread = None


def _monitor_loop() -> None:
    """
    Poll every registered pin; log only on edges (open→triggered or reverse).
    Runs until _monitor_stop is set.
    """
    while not _monitor_stop.is_set():
        if _gpio_available:
            try:
                import RPi.GPIO as GPIO  # type: ignore
                for name, pin in LIMIT_SWITCH_PINS.items():
                    # Pin LOW = switch closed = triggered
                    triggered = GPIO.input(pin) == GPIO.LOW
                    previous = _last_states.get(name)
                    if previous is None:
                        _last_states[name] = triggered
                        continue
                    if triggered and not previous:
                        log.info(
                            "LIMIT SWITCH TRIGGERED  %s  (BCM pin %d)",
                            name, pin,
                        )
                    elif not triggered and previous:
                        log.info(
                            "LIMIT SWITCH RELEASED   %s  (BCM pin %d)",
                            name, pin,
                        )
                    _last_states[name] = triggered
            except Exception as exc:
                # Transient read errors should not kill the monitor
                log.error("GPIO monitor read error: %s", exc)
        _monitor_stop.wait(_MONITOR_POLL_S)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def read_limit_switches() -> dict[str, bool]:
    """
    Return the current state of every registered limit switch.

    Returns:
        dict  name → triggered (True = pin LOW = switch closed)

    Example:
        {"X_MIN": False, "Y_MIN": False, "Z_MIN": True}
    """
    if not _gpio_available:
        return {name: False for name in LIMIT_SWITCH_PINS}

    try:
        import RPi.GPIO as GPIO  # type: ignore
        return {
            name: GPIO.input(pin) == GPIO.LOW
            for name, pin in LIMIT_SWITCH_PINS.items()
        }
    except Exception as exc:
        log.error("read_limit_switches error: %s", exc)
        return {name: False for name in LIMIT_SWITCH_PINS}


def is_triggered(switch_name: str) -> bool:
    """
    Return True if the named limit switch is currently triggered (pin LOW).

    Args:
        switch_name: e.g. "X_MIN", "Y_MIN", "Z_MIN"
    """
    if not _gpio_available:
        return False
    pin = LIMIT_SWITCH_PINS.get(switch_name)
    if pin is None:
        log.warning("is_triggered: unknown switch '%s'", switch_name)
        return False
    try:
        import RPi.GPIO as GPIO  # type: ignore
        return GPIO.input(pin) == GPIO.LOW
    except Exception as exc:
        log.error("is_triggered error: %s", exc)
        return False


def gpio_available() -> bool:
    """True if GPIO was successfully initialised."""
    return _gpio_available
