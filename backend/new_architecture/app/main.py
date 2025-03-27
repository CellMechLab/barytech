from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.message_processor import broadcast_messages, batch_processor
from app.mqtt_client import start_mqtt_client,get_mqtt_client
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
    "http://127.0.0.1:3000"
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

@app.on_event("startup")
async def startup_event():
    import app.shared_state
    app.shared_state.main_event_loop = asyncio.get_event_loop()
    # start_mqtt_client()
    # asyncio.create_task(broadcast_messages())
    # asyncio.create_task(batch_processor())

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
        try:
            first_message = await websocket.receive_text()
            client_data = json.loads(first_message)
            client_id = client_data.get("client_id")
        except Exception as e:
            print("Failed to receive client_id:", e)
            await websocket.close()
            return
        
        if not client_id:
            print("client_id missing; closing connection")
            await websocket.close()
            return
        
        print(f"Connected client ID: {client_id}")
        
        # Save client session asynchronously
        await save_client_session(db, client_id, str(websocket))
        
        # Add WebSocket connection to the dictionary
        websocket_connections[client_id] = set()  # When a user connects
        websocket_connections[client_id].add(websocket)
        
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
    if save_flag:
        print("Save data action triggered!")
    else:
        print("Save data action disabled.")