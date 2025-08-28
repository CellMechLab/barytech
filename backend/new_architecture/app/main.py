from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.message_processor import broadcast_messages, batch_processor, global_message_processor
from app.mqtt_client import process_raw_messages
from app.mqtt_client import start_mqtt_client, get_mqtt_client
from fastapi import WebSocket, WebSocketDisconnect
from app.db import get_db, save_client_session, mark_client_disconnected
from fastapi.middleware.cors import CORSMiddleware
import json
import asyncio
from app.websocket_manager import websocket_connections  # Import the WebSocket connections dictionary
from .auth import router as auth_router  # Import your auth router
import threading
from app.shared_state import save_flag, main_event_loop
from app.routers import router  # Import your router
from strawberry.asgi import GraphQL
import strawberry
from strawberry.fastapi import GraphQLRouter
from app.metrics import router as metrics_router  # Import Prometheus metrics router

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

app = FastAPI()

origins = [
    # "http://localhost",
    # "http://localhost:8080",  # Adjust based on your frontend's address
    "http://localhost:3000",
    "http://127.0.0.1:3001",
    "http://localhost:3001",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
graphql_app = GraphQLRouter(schema, subscription_protocols=["graphql-ws"])

app.include_router(auth_router)
app.include_router(router, prefix="/api", tags=["IoT Devices"])  # Optional: Add prefix or tags for grouping
app.include_router(graphql_app, prefix="/graphql")
app.include_router(metrics_router)  # Mount Prometheus metrics endpoint

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

@app.on_event("startup")
async def startup_event():
    import app.shared_state
    app.shared_state.main_event_loop = asyncio.get_event_loop()
    
    # Start the raw message processor for high-throughput message handling
    asyncio.create_task(process_raw_messages())
    
    # Start the global message processor for device-specific processing
    asyncio.create_task(global_message_processor())
    
    # Start monitoring stats printing
    from app.mqtt_client import start_monitoring
    asyncio.create_task(start_monitoring())

    mqtt_thread = threading.Thread(target=start_mqtt_client)
    mqtt_thread.start()

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

def handle_save_flag(flag):
    import app.shared_state
    app.shared_state.save_flag = flag
    if flag:
        print("Save data action triggered!")
    else:
        print("Save data action disabled.")