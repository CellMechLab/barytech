# from fastapi import WebSocket, WebSocketDisconnect
# from app.db import get_db, save_device_data, mark_message_as_sent, save_client_session, mark_client_disconnected
# from fastapi.middleware.cors import CORSMiddleware
# import json

websocket_connections = {}

# async def websocket_endpoint(websocket: WebSocket):
#     print("websocket_endpoint")
#     db = next(get_db())
#     await websocket.accept()
#     client_id = ""
#     print(f"Connected client: {websocket}")
#     # Save client session
#     save_client_session(db, client_id, str(websocket))

#     # Add WebSocket connection to the dictionary
#     websocket_connections[client_id] = websocket

#     # Send buffered messages if they exist
#     unsent_messages = get_unsent_messages(db, client_id)
#     if unsent_messages:
#         for msg in unsent_messages:
#             print("sending unsent messages")
#             await websocket.send_text(json.dumps(msg.message_data))
#             mark_message_as_sent(db, msg.id)

#     try:
#         while True:
#             data = await websocket.receive_text()
#             # Process the received message and forward to MQTT broker
#             # Publish to MQTT
#     except WebSocketDisconnect:
#         mark_client_disconnected(db, client_id)
#         websocket_connections.pop(client_id, None)