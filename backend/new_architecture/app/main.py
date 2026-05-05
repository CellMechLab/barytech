"""FastAPI application entrypoint for WebSocket, printer, and MQTT services."""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from app.message_processor import broadcast_messages, batch_processor, global_message_processor
from app.mqtt_client import process_raw_messages
from app.mqtt_client import start_mqtt_client, get_mqtt_client
from app.db import get_db, save_client_session, mark_client_disconnected
import json
import asyncio
import threading
from contextlib import asynccontextmanager
from app.websocket_manager import websocket_connections
from .auth import router as auth_router
from app.shared_state import save_flag, main_event_loop
from app.routers import router
from strawberry.asgi import GraphQL
import strawberry
from strawberry.fastapi import GraphQLRouter
from app.metrics import router as metrics_router
from app.printer_router import printer_service, get_printer_status


@strawberry.type
class Query:
    hello: str = "Hello World"

@strawberry.type
class Subscription:
    @strawberry.subscription
    async def greetings(self) -> str:
        for name in ["Alice", "Bob", "Charlie"]:
            yield f"Hello, {name}!"

schema = strawberry.Schema(query=Query, subscription=Subscription)
# graphql_app = GraphQLRouter(schema)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Stores background task for draining MQTT thread queue into async processing.
    raw_message_processor_task = None
    # Stores background task for periodic MQTT/processing monitoring logs.
    monitoring_task = None

    # Open persistent WebSocket connection to the Pi on startup.
    await printer_service.connect()

    # Initialize MQTT client and subscribe to broker topics during API startup.
    start_mqtt_client()
    # Runs continuous raw-message batch processing without blocking startup.
    raw_message_processor_task = asyncio.create_task(process_raw_messages())
    # Runs periodic monitoring output for pipeline health and throughput visibility.
    from app.mqtt_client import start_monitoring
    monitoring_task = asyncio.create_task(start_monitoring())

    yield

    # Prevent noisy cancellation warnings when stopping background worker tasks.
    if raw_message_processor_task:
        raw_message_processor_task.cancel()
        try:
            await raw_message_processor_task
        except asyncio.CancelledError:
            pass
    # Prevent noisy cancellation warnings when stopping periodic monitor task.
    if monitoring_task:
        monitoring_task.cancel()
        try:
            await monitoring_task
        except asyncio.CancelledError:
            pass

    # Close cleanly on shutdown.
    await printer_service.disconnect()


app = FastAPI(lifespan=lifespan)

origins = [
    "*"
    # "http://localhost",
    # "http://localhost:8080",  # Adjust based on your frontend's address
    # "http://localhost:3000",
    # "http://127.0.0.1:3001",
    # "http://localhost:3001",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(router, prefix="/api", tags=["IoT Devices"])  # Optional: Add prefix or tags for grouping
app.include_router(metrics_router)  # Mount Prometheus metrics endpoint
from app.printer_router import router as printer_router
app.include_router(printer_router)

@app.get("/monitoring/stats")
async def get_monitoring_stats():
    """Get comprehensive monitoring statistics."""
    from app.mqtt_client import get_message_stats
    from app.message_processor import get_processing_stats
    
    mqtt_stats = get_message_stats()
    processing_stats = get_processing_stats()
    
    # Combine stats
    combined_stats = {
        **mqtt_stats,
        **processing_stats,
        "total_messages_sent_to_frontend": 0  # This will be updated from message_processor
    }
    
    # Get total messages sent to frontend from message_processor
    from app.message_processor import total_messages_sent_to_frontend
    combined_stats["total_messages_sent_to_frontend"] = total_messages_sent_to_frontend
    
    return combined_stats

@app.get("/monitoring/health")
async def get_health_status():
    """Get system health status."""
    from app.mqtt_client import get_message_stats
    from app.message_processor import get_processing_stats
    
    mqtt_stats = get_message_stats()
    processing_stats = get_processing_stats()
    
    # Calculate health metrics
    total_received = mqtt_stats.get("mqtt_received", 0)
    total_parsed = mqtt_stats.get("mqtt_parsed", 0)
    total_processed = processing_stats.get("device_processed", 0)
    total_broadcast = processing_stats.get("broadcast_sent", 0)
    
    # Calculate success rates
    parsing_success_rate = (total_parsed / total_received * 100) if total_received > 0 else 100
    processing_success_rate = (total_processed / total_parsed * 100) if total_parsed > 0 else 100
    broadcast_success_rate = (total_broadcast / total_processed * 100) if total_processed > 0 else 100
    
    health_status = {
        "status": "healthy",
        "parsing_success_rate": round(parsing_success_rate, 2),
        "processing_success_rate": round(processing_success_rate, 2),
        "broadcast_success_rate": round(broadcast_success_rate, 2),
        "total_messages_received": total_received,
        "total_messages_processed": total_processed,
        "total_messages_broadcast": total_broadcast
    }
    
    # Mark as unhealthy if any success rate is below 95%
    if parsing_success_rate < 95 or processing_success_rate < 95 or broadcast_success_rate < 95:
        health_status["status"] = "degraded"
    
    return health_status

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    print("websocket connection")
    
    # client_id = websocket.scope.get("client_id")
    # if not client_id:
    #     await websocket.close()
    #     return

    # print(f"Client ID from connection params: {client_id}")
    # Use the async database session
    async with get_db() as db:
        await websocket.accept()
        # Use a default client_id if none is provided
        client_id = "1"  # Default client ID for all connections
        try:
            first_message = await websocket.receive_text()
            client_data = json.loads(first_message)
            if client_data.get("client_id"):
                client_id = str(client_data.get("client_id"))  # Ensure it's a string
        except Exception as e:
            print("No client_id provided, using default:", e)
            # Continue with default client_id
        
        print(f"Connected client ID: {client_id}")
        
        # Save client session asynchronously
        await save_client_session(db, client_id, str(websocket))
        
        # Add WebSocket connection to the dictionary
        if client_id not in websocket_connections:
            websocket_connections[client_id] = set()
        websocket_connections[client_id].add(websocket)
        print(f"WebSocket added to connections. Total connections for {client_id}: {len(websocket_connections[client_id])}")
        print(f"All websocket_connections: {websocket_connections}")
        
        try:
            while True:
                # Receive data from WebSocket
                data = await websocket.receive_text()
                params = json.loads(data)
                print(f"Received from WebSocket: {params}")
                
                # Check message type
                message_type = params.get("type")
                
                if message_type == "slider":
                    # Handle slider updates
                    mqtt_client = get_mqtt_client()  # Dynamically fetch the MQTT client
                    mqtt_client.publish("PAR", json.dumps(params))
                    print(f"Published slider data to PAR: {params}")
                
                elif message_type == "save":
                    # Handle save action
                    save_flag = params.get("save", False)
                    print(f"Save flag received: {save_flag}")
                    # Perform actions for save flag
                    # For example, update a global variable or call a function
                    handle_save_flag(save_flag)
                
                else:
                    print(f"Unknown message type: {message_type}")
                
                # Process the received message and forward to MQTT broker
                # Publish to MQTT
                
        except WebSocketDisconnect:
            # Mark client as disconnected asynchronously
            await mark_client_disconnected(db, client_id)
            # Remove WebSocket connection from the dictionary
            websocket_connections.pop(client_id, None)

# @app.websocket("/graphql")
# async def websocket_endpoint(websocket: WebSocket):
#     await websocket.accept()
#     print("websocket connection establised")
#     try:
#         while True:
#             message = await websocket.receive_json()
#             if message["type"] == "INIT":
#                 client_id = message.get("client_id")
#                 print(f"Client ID received: {client_id}")
#             else:
#                 print(f"Unexpected message: {message}")
#     except WebSocketDisconnect:
#         print("WebSocket disconnected")

# Interval in seconds between printer status pushes over /ws/printer
_PRINTER_STATUS_INTERVAL = 2.0

# Actions the frontend is allowed to trigger over /ws/printer
_ALLOWED_PRINTER_ACTIONS = {
    "connect", "disconnect", "status",
    "move", "move_up",
    "position", "temperature",
    "gcode", "emergency_stop",
}


@app.websocket("/ws/printer")
async def printer_status_ws(websocket: WebSocket):
    """
    Bidirectional WebSocket for the printer dashboard.

    ── Server → Client (push, every _PRINTER_STATUS_INTERVAL seconds) ──────
        {
          "type":         "printer_status",
          "position":     { "X": float, "Y": float, "Z": float, "E": float },
          "temperatures": { "hotend_temp": float|null, "bed_temp": float|null }
        }

    ── Client → Server (command frames) ────────────────────────────────────
        { "action": "move",    "params": { "axis": "X", "distance": 10.0 } }
        { "action": "move_up", "params": { "distance": 1.0, "feed": 1200 } }
        { "action": "gcode",   "params": { "command": "M503" } }
        { "action": "emergency_stop" }
        … any action listed in _ALLOWED_PRINTER_ACTIONS

    ── Server → Client (command reply) ─────────────────────────────────────
        { "type": "command_result", "action": "<action>",
          "ok": true,  "data":   { ... } }
        { "type": "command_result", "action": "<action>",
          "ok": false, "error":  "..." }
    """
    from app.printer_router import _ws_client   # shared singleton

    await websocket.accept()
    print("[/ws/printer] client connected")

    # ── Background task: push live status every N seconds ──────────────────
    async def push_loop() -> None:
        while True:
            status = await get_printer_status()
            try:
                await websocket.send_json({"type": "printer_status", **status})
            except Exception:
                break               # client gone — exit quietly
            await asyncio.sleep(_PRINTER_STATUS_INTERVAL)

    push_task = asyncio.create_task(push_loop())

    # ── Foreground: process incoming command frames ─────────────────────────
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg    = json.loads(raw)
                action = msg.get("action", "")
                params = msg.get("params") or {}
            except (json.JSONDecodeError, AttributeError):
                await websocket.send_json({
                    "type": "command_result", "action": "?",
                    "ok": False, "error": "Invalid JSON frame",
                })
                continue

            if action not in _ALLOWED_PRINTER_ACTIONS:
                await websocket.send_json({
                    "type": "command_result", "action": action,
                    "ok": False,
                    "error": f"Unknown action '{action}'. "
                             f"Allowed: {sorted(_ALLOWED_PRINTER_ACTIONS)}",
                })
                continue

            # Forward the command to the Pi via the shared WS client
            try:
                timeout = float(params.pop("timeout", 60.0)) if action == "gcode" else 60.0
                data    = await _ws_client.call(action, params, timeout=timeout)
                await websocket.send_json({
                    "type": "command_result", "action": action,
                    "ok": True, "data": data,
                })
            except Exception as exc:
                detail = getattr(exc, "detail", str(exc))
                await websocket.send_json({
                    "type": "command_result", "action": action,
                    "ok": False, "error": detail,
                })

    except WebSocketDisconnect:
        print("[/ws/printer] client disconnected")
    except Exception as exc:
        print(f"[/ws/printer] unexpected error: {exc}")
    finally:
        push_task.cancel()


def handle_save_flag(flag):
    import app.shared_state
    app.shared_state.save_flag = flag
    if flag:
        print("Save data action triggered!")
    else:
        print("Save data action disabled.")