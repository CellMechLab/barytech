"""
gpio_manager.py — Raspberry Pi GPIO manager for limit switches.

Uses RPi.GPIO directly (no gpiozero dependency).

Wiring convention:
    Each limit switch is wired between a BCM GPIO pin and GND.
    The internal pull-up resistor is enabled, so:
        Pin HIGH (1) = switch open   (not triggered)
        Pin LOW  (0) = switch closed (triggered)

Pin assignment (BCM numbering) — edit to match your wiring:
    X_MIN → GPIO 4
    Y_MIN → GPIO 27   (uncomment when wired)
    Z_MIN → GPIO 22   (uncomment when wired)
"""

import logging

log = logging.getLogger("gpio")

# ---------------------------------------------------------------------------
# Pin map  —  BCM GPIO pin numbers, edit to match your physical wiring.
# Comment out any axis whose switch is not yet physically wired.
# ---------------------------------------------------------------------------

LIMIT_SWITCH_PINS: dict[str, int] = {
    "X_MIN": 4,
    # "Y_MIN": 27,
    # "Z_MIN": 22,
}

# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------

_gpio_available: bool = False


# ---------------------------------------------------------------------------
# Init / cleanup
# ---------------------------------------------------------------------------

def init_gpio() -> None:
    """
    Initialise all limit-switch GPIO pins using RPi.GPIO directly.
    Safe to call when no pins are configured — skips silently.
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
            log.info("GPIO INIT  %s → BCM pin %d", name, pin)
        _gpio_available = True
        log.info("GPIO ready — %d limit switches registered", len(LIMIT_SWITCH_PINS))

    except (ImportError, Exception) as exc:
        log.warning(
            "GPIO init failed (%s). Running without GPIO "
            "(all switches report 'open').",
            exc,
        )
        _gpio_available = False


def cleanup_gpio() -> None:
    """Release all GPIO resources."""
    if not _gpio_available:
        return
    try:
        import RPi.GPIO as GPIO  # type: ignore
        GPIO.cleanup()
        log.info("GPIO cleanup complete")
    except Exception as exc:
        log.warning("GPIO cleanup error: %s", exc)


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