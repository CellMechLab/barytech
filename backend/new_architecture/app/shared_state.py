# shared_state.py
import asyncio
from typing import Dict, Optional

# Global variable to hold the main asyncio event loop
main_event_loop = None

# True while the frontend has an active save session open.
save_flag = False

# Folder id currently targeted by the active save session; None when save is off.
current_folder_id: Optional[int] = None

# Zero-based curve index currently being recorded for the active folder.
current_curve_index: int = 0

# In-memory counter: folder_id → number of ON→OFF save cycles completed so far.
# Incremented on every False→True transition so each new save gets a fresh index.
folder_curve_index_map: Dict[int, int] = {}

# Optional metadata dict for the active folder/experiment (velocity, conversion factors, tip params).
current_folder_metadata: Optional[dict] = None
