# websocket_manager.py
# WebSocket connection management and message handling
import json
from fastapi import WebSocket, WebSocketDisconnect
from app.shared_state import set_save_mode


# Dictionary to store WebSocket connections by client_id
websocket_connections = {}


async def handle_websocket_message(data: dict, websocket: WebSocket):
    """
    Handle incoming WebSocket messages and route them to appropriate handlers.
    
    Args:
        data: Parsed JSON message from WebSocket
        websocket: The WebSocket connection object
    """
    msg_type = data.get("type")
    
    # ------------------------------
    # 🔥 Handle SAVE MODE toggling
    # ------------------------------
    if msg_type == "save":
        device_id = data.get("device_id")  # Can be None for global mode
        save = bool(data.get("save", False))
        
        # Set save mode (per-device if device_id provided, global if None)
        set_save_mode(device_id, save)
        
        if device_id:
            print(f"🔥 SAVE MODE SET: device={device_id}, save={save}")
        else:
            print(f"🔥 GLOBAL SAVE MODE SET: save={save}")
    
    # ------------------------------
    # Other message types (connect, request_historical, etc.)
    # ------------------------------
    elif msg_type == "connect":
        print("Client connected", data)
    
    elif msg_type == "request_historical":
        print("Client requested history")
        # TODO: Implement historical data retrieval
    
    elif msg_type == "slider":
        print("Slider update received", data)
        # TODO: Handle slider updates (forward to MQTT, etc.)
    
    else:
        print(f"Unknown message type: {msg_type}")


async def websocket_endpoint(websocket: WebSocket):
    """
    Main WebSocket endpoint handler.
    Accepts connections, receives messages, and processes them.
    """
    await websocket.accept()
    
    # Extract client_id from first message
    client_id = "1"  # Default client ID
    try:
        first_message = await websocket.receive_text()
        data = json.loads(first_message)
        if data.get("client_id"):
            client_id = str(data.get("client_id"))
    except Exception as e:
        print(f"No client_id provided, using default: {e}")
    
    # Store WebSocket connection
    if client_id not in websocket_connections:
        websocket_connections[client_id] = set()
    websocket_connections[client_id].add(websocket)
    
    print(f"Connected client ID: {client_id}")
    
    try:
        while True:
            # Receive raw message from WebSocket
            raw = await websocket.receive_text()
            data = json.loads(raw)
            
            # Process the message
            await handle_websocket_message(data, websocket)
    
    except WebSocketDisconnect:
        print("Client disconnected:", client_id)
        if client_id in websocket_connections:
            websocket_connections[client_id].discard(websocket)
            if not websocket_connections[client_id]:
                websocket_connections.pop(client_id, None)