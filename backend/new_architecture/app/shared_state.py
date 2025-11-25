# shared_state.py
# Shared state management for device runtime configuration
import asyncio
from typing import Dict, Optional

# Global variable to hold the main asyncio event loop
main_event_loop: Optional[asyncio.AbstractEventLoop] = None

# Global default: send-to-frontend & forget (False = no DB writes)
save_flag: bool = False

# Optional per-device overrides
_device_save_flags: Dict[str, bool] = {}


def set_save_mode(device_id: Optional[str], flag: bool) -> None:
    """
    If device_id is provided -> set per-device save mode.
    If device_id is None -> set global default for all devices.
    """
    global save_flag

    if device_id:
        _device_save_flags[device_id] = flag
    else:
        # Change global default
        save_flag = flag


def is_save_enabled(device_id: str) -> bool:
    """
    Return True if saving is enabled for this device.
    Per-device flag overrides global default.
    """
    # Per-device override, falls back to global save_flag
    return _device_save_flags.get(device_id, save_flag)
