"""
local_agent.py — runs on Device A (on-premise).

Watches the local HDF5 folder and POST-uploads every new file to
Device B's cloud FastAPI endpoint (/hdf5/ingest) over HTTPS.

Features
────────
• Polling-based watcher (same stability guard as hdf5_watcher.py)
• Per-file retry with exponential back-off (survives network blips)
• Local SQLite ledger — never re-uploads a file across restarts
• Streams the file body so large HDF5 files don't load into RAM
• API-key authentication (X-Api-Key header)

Usage
─────
    python local_agent.py

    # or with overrides:
    AGENT_WATCH_DIR=data/barytech \
    AGENT_TARGET_URL=https://mycloud.example.com \
    AGENT_API_KEY=secret-key-here \
    python local_agent.py

Stop with Ctrl-C.
"""

import logging
import os
import signal
import threading
import sqlite3
import sys
import time
from pathlib import Path

import httpx          # pip install httpx
from dotenv import load_dotenv   # pip install python-dotenv (already in your requirements)

# Load .env from the project root (one level up from wherever this file lives)
load_dotenv(Path(__file__).parent / ".env")   # if local_agent.py is in new_architecture/


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("local_agent")

# ---------------------------------------------------------------------------
# Stop event — set externally (e.g. from main.py lifespan) to request a clean
# shutdown, or left as None when the script is run standalone (uses SIGINT).
_stop_event: "threading.Event | None" = None

# ---------------------------------------------------------------------------
# Config from environment
# All variables are prefixed AGENT_ to avoid collisions with pydantic-settings
# which raises extra_forbidden if it finds unknown env vars in Settings models.
# ---------------------------------------------------------------------------

WATCH_DIR       = Path(os.getenv("AGENT_WATCH_DIR",  "data/barytech"))
POLL_INTERVAL   = float(os.getenv("AGENT_POLL_INTERVAL",  "5.0"))
STABILITY_SECS  = float(os.getenv("AGENT_STABILITY_SECS", "2.0"))
DEVICE_B_URL    = os.getenv("AGENT_TARGET_URL",    "https://mycloud.example.com")
API_KEY         = os.getenv("AGENT_API_KEY", "change-me")
LEDGER_DB       = os.getenv("AGENT_LEDGER_DB",  "uploaded_files.db")
GLOB_PATTERNS   = ["**/*.h5", "**/*.hdf5"]

# Retry settings
MAX_RETRIES     = 5
RETRY_BASE_SECS = 2.0    # doubles each attempt: 2, 4, 8, 16, 32 s
UPLOAD_TIMEOUT  = 120.0  # seconds — raise for very large files

# ---------------------------------------------------------------------------
# Local SQLite ledger (tracks uploaded files so we never re-upload)
# ---------------------------------------------------------------------------

class Ledger:
    def __init__(self, db_path: str = LEDGER_DB):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS uploaded (
                abs_path TEXT PRIMARY KEY,
                uploaded_at TEXT DEFAULT (datetime('now'))
            )
        """)
        self._conn.commit()

    def is_uploaded(self, path: Path) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM uploaded WHERE abs_path = ?", (str(path.resolve()),)
        )
        return cur.fetchone() is not None

    def mark_uploaded(self, path: Path) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO uploaded (abs_path) VALUES (?)",
            (str(path.resolve()),),
        )
        self._conn.commit()


# ---------------------------------------------------------------------------
# Upload a single file with retry
# ---------------------------------------------------------------------------

def upload_file(path: Path, client: httpx.Client) -> bool:
    """
    POST the file to Device B's /hdf5/ingest endpoint.
    Returns True on success, False after all retries exhausted.

    Uses httpx streaming so the file is never fully loaded into memory.
    """
    url = f"{DEVICE_B_URL.rstrip('/')}/hdf5/ingest"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            log.info("Uploading  file=%s  attempt=%d/%d", path.name, attempt, MAX_RETRIES)
            with open(path, "rb") as fh:
                response = client.post(
                    url,
                    content=fh,                       # streamed — no RAM spike
                    headers={
                        "X-Api-Key":      API_KEY,
                        "X-Filename":     path.name,
                        "Content-Type":   "application/octet-stream",
                    },
                    timeout=UPLOAD_TIMEOUT,
                )
            if response.status_code == 200:
                log.info("Upload OK  file=%s  response=%s", path.name, response.json())
                return True
            else:
                log.warning(
                    "Upload rejected  file=%s  status=%d  body=%s",
                    path.name, response.status_code, response.text[:200],
                )
                # 4xx = bad request, don't retry (it will keep failing)
                if 400 <= response.status_code < 500:
                    return False

        except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as exc:
            log.warning("Network error  attempt=%d  error=%s", attempt, exc)
        except Exception:
            log.exception("Unexpected error uploading %s", path)

        if attempt < MAX_RETRIES:
            wait = RETRY_BASE_SECS * (2 ** (attempt - 1))
            log.info("Retrying in %.0f s …", wait)
            time.sleep(wait)

    log.error("Giving up on %s after %d attempts", path.name, MAX_RETRIES)
    return False


# ---------------------------------------------------------------------------
# Stability check (identical logic to hdf5_watcher.py)
# ---------------------------------------------------------------------------

def _file_is_stable(path: Path, secs: float) -> bool:
    try:
        before = path.stat().st_size
    except OSError:
        return False
    time.sleep(secs)
    try:
        after = path.stat().st_size
    except OSError:
        return False
    return before == after and before > 0


# ---------------------------------------------------------------------------
# Main polling loop
# ---------------------------------------------------------------------------

def main() -> None:
    # When embedded in FastAPI the thread must never call sys.exit() —
    # that raises SystemExit inside the thread which bubbles up as a noisy
    # traceback without actually stopping the process.  Instead we retry
    # until the directory appears (e.g. a mount that isn't ready yet) or
    # the stop event is signalled.
    stop_event = _stop_event if _stop_event is not None else threading.Event()
    if not WATCH_DIR.exists():
        log.warning(
            "Watch directory does not exist yet: %s — "
            "retrying every %.0f s until it appears or app shuts down",
            WATCH_DIR, POLL_INTERVAL,
        )
        while not WATCH_DIR.exists():
            if stop_event.is_set():
                log.info("Stop requested before watch dir appeared — exiting agent")
                return
            stop_event.wait(timeout=POLL_INTERVAL)
        log.info("Watch directory now available: %s", WATCH_DIR)

    ledger = Ledger()

    # Stores shared request headers for every upload call.
    client_headers = {"X-Api-Key": API_KEY}
    # Prevent crash when optional HTTP/2 dependencies are not installed.
    try:
        # Shared HTTP client — reuses connections, has built-in connection pooling
        client = httpx.Client(
            headers=client_headers,
            http2=True,   # Device B's cloud server likely supports HTTP/2
        )
    except ImportError:
        log.warning("http2 extras missing; falling back to HTTP/1.1 client")
        # Uses a compatible HTTP/1.1 client when HTTP/2 support is unavailable.
        client = httpx.Client(headers=client_headers)

    # Signal handlers can only be registered from the main thread.
    # When embedded inside FastAPI the lifespan owns signal handling,
    # so we skip this block — the stop_event will be set externally.
    if threading.current_thread() is threading.main_thread():
        def _on_signal(*_):
            log.info("Shutdown signal — finishing current file then stopping")
            stop_event.set()
        signal.signal(signal.SIGINT,  _on_signal)
        signal.signal(signal.SIGTERM, _on_signal)

    log.info("Agent started  watch=%s  target=%s", WATCH_DIR, DEVICE_B_URL)

    while not stop_event.is_set():
        candidates: list[Path] = []
        for pattern in GLOB_PATTERNS:
            try:
                candidates.extend(WATCH_DIR.glob(pattern))
            except Exception as exc:
                log.warning("glob error: %s", exc)

        new_files = [p for p in candidates if not ledger.is_uploaded(p)]

        for path in new_files:
            if stop_event.is_set():
                break

            if not _file_is_stable(path, STABILITY_SECS):
                log.debug("File still being written — skipping  file=%s", path.name)
                continue

            if ledger.is_uploaded(path):
                continue    # another iteration may have got it

            ok = upload_file(path, client)
            if ok:
                ledger.mark_uploaded(path)

        if not stop_event.is_set():
            time.sleep(POLL_INTERVAL)

    client.close()
    log.info("Agent stopped.")


if __name__ == "__main__":
    main()# placeholder — will be replaced below