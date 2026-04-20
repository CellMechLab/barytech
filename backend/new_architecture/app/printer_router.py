"""
app/printer_router.py

Proxy router: PC backend ↔ Raspberry Pi printer service via WebSocket.

The Pi runs printer_control.py (FastAPI + WebSocket at /ws).
This module maintains ONE persistent WebSocket connection to the Pi and
multiplexes all REST endpoint calls over it using per-request UUID
correlation IDs, so concurrent HTTP handlers never block each other.

──────────────────────────────────────────────────────────────────────────────
Wire into main.py
─────────────────
    from app.printer_router import router as printer_router, printer_service
    app.include_router(printer_router)

    # In your lifespan:
    @asynccontextmanager
    async def lifespan(app):
        await printer_service.connect()          # open WS to Pi on boot
        yield
        await printer_service.disconnect()       # close on shutdown

Set the Pi address via environment variable:
    PRINTER_WS_URL=ws://192.168.1.42:8001/ws

Auto-reconnect behaviour
────────────────────────
  • The _WsClient reconnects the WebSocket automatically before every send if
    the connection is found closed.
  • If the Pi's printer_control returns a 503 (serial port not open), the
    client will auto-send a 'connect' action to open it, then replay the
    original request once.  Callers never need to manually sequence
    /printer/connect before motion commands.
──────────────────────────────────────────────────────────────────────────────
"""

import asyncio
import json
import os
import uuid
from typing import Optional

import websockets
import websockets.exceptions
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PRINTER_WS_URL: str = os.getenv(
    "PRINTER_WS_URL", "ws://10.99.134.8:8003/ws"
)

router = APIRouter(prefix="/printer", tags=["3D Printer"])


# ---------------------------------------------------------------------------
# _WsClient — persistent, multiplexed WebSocket connection
# ---------------------------------------------------------------------------

class _WsClient:
    """
    Manages a single persistent WebSocket connection to the Pi printer service.

    Design notes
    ────────────
    • Concurrent callers each get their own asyncio.Future keyed by a UUID.
      The background _receive_loop resolves futures as frames arrive, so many
      REST handlers can be in-flight simultaneously over one socket.
    • _connect_lock serialises reconnect attempts so only one coroutine
      re-opens the socket at a time even under concurrent load.
    • If the socket drops while requests are pending, _receive_loop rejects
      all outstanding futures immediately so callers don't hang.
    """

    def __init__(self, url: str) -> None:
        self._url           = url
        self._ws            = None          # websockets.connect() return type varies by version
        self._connect_lock  = asyncio.Lock()
        self._pending: dict[str, asyncio.Future] = {}
        self._recv_task: Optional[asyncio.Task]  = None

    # ------------------------------------------------------------------
    # Version-safe open check
    # ------------------------------------------------------------------

    @staticmethod
    def _ws_open(ws) -> bool:
        """
        Return True if *ws* is an open WebSocket connection.

        websockets ≥ 11 replaced WebSocketClientProtocol (which had a
        .closed bool) with ClientConnection (which exposes .state).
        This helper handles both so the rest of the class stays clean.
        """
        if ws is None:
            return False
        # websockets ≥ 11: connection object exposes .state
        state = getattr(ws, "state", None)
        if state is not None:
            try:
                from websockets.connection import State
                return state is State.OPEN
            except ImportError:
                # Fallback: any non-OPEN name means not open
                return getattr(state, "name", "") == "OPEN"
        # websockets < 11: .closed bool attribute
        return not getattr(ws, "closed", True)

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the WebSocket connection to the Pi and start the receive loop."""
        async with self._connect_lock:
            await self._open()

    async def disconnect(self) -> None:
        """Gracefully close the WebSocket and cancel the receive loop."""
        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
        if self._ws:
            await self._ws.close()
            self._ws = None

    @property
    def is_connected(self) -> bool:
        return self._ws_open(self._ws)

    # ------------------------------------------------------------------
    # Internal open (must be called while holding _connect_lock)
    # ------------------------------------------------------------------

    async def _open(self) -> None:
        if self._ws_open(self._ws):
            return                          # already open

        # Cancel stale receive task before reconnecting
        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()

        try:
            self._ws = await websockets.connect(
                self._url,
                ping_interval=20,
                ping_timeout=10,
                open_timeout=10,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Cannot connect to printer service at {self._url}: {exc}. "
                    "Check that the Raspberry Pi is on the network and "
                    "printer_control.py is running."
                ),
            )

        self._recv_task = asyncio.create_task(self._receive_loop())

    # ------------------------------------------------------------------
    # Background receive loop
    # ------------------------------------------------------------------

    async def _receive_loop(self) -> None:
        """
        Reads frames continuously and resolves the matching pending Future.
        When the connection closes, all outstanding Futures are rejected so
        their callers surface a ConnectionError instead of hanging forever.
        """
        try:
            async for raw in self._ws:
                try:
                    msg    = json.loads(raw)
                    msg_id = msg.get("id")
                    if msg_id and msg_id in self._pending:
                        fut = self._pending.pop(msg_id)
                        if not fut.done():
                            fut.set_result(msg)
                except json.JSONDecodeError:
                    pass    # malformed frame — skip silently
        except Exception:
            pass
        finally:
            # Reject all in-flight requests so callers are not left hanging
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(
                        ConnectionError(
                            "WebSocket connection to printer service was lost"
                        )
                    )
            self._pending.clear()

    # ------------------------------------------------------------------
    # call() — send an action, await a response
    # ------------------------------------------------------------------

    async def call(
        self,
        action: str,
        params: Optional[dict] = None,
        *,
        timeout: float = 30.0,
        _retry: bool = True,    # internal flag — prevents infinite retry loops
    ) -> dict:
        """
        Send an action to the Pi and return the 'data' dict on success.

        Raises HTTPException for:
            503  Cannot reach the Pi / serial port not open (after retry)
            504  Printer service did not respond within *timeout* seconds
            4xx/5xx  Error response from the Pi
        """
        # Auto-reconnect WebSocket if needed
        if not self.is_connected:
            async with self._connect_lock:
                await self._open()

        msg_id  = str(uuid.uuid4())
        loop    = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[msg_id]  = future

        payload = json.dumps({"id": msg_id, "action": action, "params": params or {}})

        try:
            await self._ws.send(payload)
        except Exception as exc:
            self._pending.pop(msg_id, None)
            raise HTTPException(
                status_code=503,
                detail=f"Failed to send to printer service: {exc}",
            )

        try:
            response = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            raise HTTPException(
                status_code=504,
                detail=f"Printer service timed out for action '{action}'",
            )
        except ConnectionError as exc:
            raise HTTPException(status_code=503, detail=str(exc))

        # ── Handle error responses ────────────────────────────────────────
        if response.get("status") == "error":
            code   = response.get("code", 500)
            detail = response.get("detail", "Unknown printer error")

            # 503 means the Pi's serial port is not open yet — connect then retry once
            if code == 503 and action != "connect" and _retry:
                print(
                    f"[printer_router] Pi returned 503 for '{action}'; "
                    "auto-connecting serial port then retrying."
                )
                await self.call("connect", timeout=15.0, _retry=False)
                return await self.call(action, params, timeout=timeout, _retry=False)

            raise HTTPException(status_code=code, detail=detail)

        return response.get("data", {})


# ---------------------------------------------------------------------------
# Singleton client
# ---------------------------------------------------------------------------

_ws_client = _WsClient(PRINTER_WS_URL)


# ---------------------------------------------------------------------------
# PrinterService — async lifecycle wrapper used by main.py lifespan
# ---------------------------------------------------------------------------

class PrinterService:
    """
    Async lifecycle helpers so main.py can open/close the WebSocket connection
    during application startup and shutdown.

    Usage in main.py lifespan:
        @asynccontextmanager
        async def lifespan(app):
            await printer_service.connect()
            yield
            await printer_service.disconnect()
    """

    @property
    def is_connected(self) -> bool:
        return _ws_client.is_connected

    async def connect(self) -> None:
        try:
            await _ws_client.connect()
            print(f"[PrinterService] WebSocket connected → {PRINTER_WS_URL}")
        except HTTPException as exc:
            # Non-fatal at boot — the printer may not be reachable yet
            print(f"[PrinterService] connect failed (Pi may be offline): {exc.detail}")

    async def disconnect(self) -> None:
        try:
            await _ws_client.disconnect()
            print("[PrinterService] WebSocket disconnected")
        except Exception as exc:
            print(f"[PrinterService] disconnect failed: {exc}")


printer_service = PrinterService()


# ---------------------------------------------------------------------------
# get_printer_status() — used by the /ws/printer push loop in main.py
# ---------------------------------------------------------------------------

async def get_printer_status() -> dict:
    """
    Fetch live position + temperatures from the Pi in a single WebSocket call.

    Returns a dict with keys:
        position     – { X, Y, Z, E }          (empty dict when offline)
        temperatures – { hotend_temp, bed_temp } (None values when offline)

    Never raises — returns safe fallback values so the push loop keeps running.
    """
    try:
        return await _ws_client.call("printer_status", timeout=10.0)
    except (HTTPException, Exception) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        print(f"[get_printer_status] failed: {detail}")
        return {
            "position":     {},
            "temperatures": {"hotend_temp": None, "bed_temp": None},
        }


# ---------------------------------------------------------------------------
# Connection routes
# ---------------------------------------------------------------------------

@router.post("/connect", summary="Open serial port on the Pi")
async def connect(body: dict = Body(default={})):
    """
    Send a 'connect' action to the Pi.
    Accepts optional printer config fields: port, baud_rate, timeout,
    feed_xy, feed_z, feed_e.
    """
    data = await _ws_client.call("connect", body, timeout=15.0)
    return JSONResponse(content=data)


@router.post("/disconnect", summary="Close serial port on the Pi")
async def disconnect():
    data = await _ws_client.call("disconnect")
    return JSONResponse(content=data)


@router.get("/status", summary="Printer connection status and config")
async def get_status():
    data = await _ws_client.call("status")
    return JSONResponse(content=data)


# ---------------------------------------------------------------------------
# Motion routes
# ---------------------------------------------------------------------------

@router.post("/move", summary="Move one axis by a relative distance")
async def move(body: dict = Body(...)):
    """
    Body: { "axis": "X", "distance": 10.0, "feed": 3000 }
    axis     – X / Y / Z / E
    distance – signed millimetres
    feed     – mm/min (optional; falls back to per-axis default on the Pi)
    """
    data = await _ws_client.call("move", body, timeout=60.0)
    return JSONResponse(content=data)


@router.post("/move-up", summary="Move Z axis up using default safe values")
async def move_up(body: dict = Body(default={})):
    """
    Convenience endpoint for a quick Z-up jog.
    Body (all optional): { "distance": 1.0, "feed": 1200 }
    """
    params = {
        "distance": float(body.get("distance", 1.0)),
        "feed":     int(body.get("feed", 1200)),
    }
    data = await _ws_client.call("move_up", params, timeout=60.0)
    return JSONResponse(content=data)


# @router.post("/home", summary="Home axes (omit body to home all)")
# async def home(body: dict = Body(default={})):
#     """
#     Body: { "axes": ["X", "Y"] }  —  omit or pass {} to home all axes.
#     """
#     data = await _ws_client.call("home", body, timeout=180.0)
#     return JSONResponse(content=data)


@router.get("/position", summary="Query current XYZ E position (M114)")
async def get_position():
    data = await _ws_client.call("position")
    return JSONResponse(content=data)


@router.get("/temperature", summary="Query hotend and bed temperatures (M105)")
async def get_temperature():
    """
    Returns: { "hotend_temp": <float|null>, "bed_temp": <float|null>, "raw": "..." }
    """
    data = await _ws_client.call("temperature", timeout=10.0)
    return JSONResponse(content=data)


# ---------------------------------------------------------------------------
# Extruder routes (disabled)
# ---------------------------------------------------------------------------

# @router.post("/extrude", summary="Extrude filament")
# async def extrude(body: dict = Body(...)):
#     """Body: { "distance": 5.0, "feed": 300 }"""
#     data = await _ws_client.call("extrude", body)
#     return JSONResponse(content=data)


# @router.post("/retract", summary="Retract filament")
# async def retract(body: dict = Body(...)):
#     """Body: { "distance": 5.0, "feed": 300 }"""
#     data = await _ws_client.call("retract", body)
#     return JSONResponse(content=data)


# ---------------------------------------------------------------------------
# Advanced routes
# ---------------------------------------------------------------------------

@router.post("/gcode", summary="Send a raw G-code command")
async def send_gcode(body: dict = Body(...)):
    """
    Body: { "command": "M503", "timeout": 10.0 }
    Returns: { "command": "...", "response": ["ok T:...", ...] }
    """
    extra    = float(body.get("timeout", 30.0)) + 5.0   # add network overhead
    data     = await _ws_client.call("gcode", body, timeout=extra)
    return JSONResponse(content=data)


@router.post("/emergency-stop", summary="M112 — firmware emergency stop")
async def emergency_stop():
    """Halts the printer firmware. A physical reboot is required to resume."""
    data = await _ws_client.call("emergency_stop", timeout=10.0)
    return JSONResponse(content=data)