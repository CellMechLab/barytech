import asyncio
import queue
import time
import json
from app.db import save_device_data_batch, get_db, get_user_id_by_device_id
from app.websocket_manager import websocket_connections  # Import the WebSocket connections dictionary
import app.shared_state
from datetime import datetime

# Global message queue for all incoming messages (no longer used)
# global_message_queue = asyncio.Queue(maxsize=100000)  # Increased queue size
device_queues = {} 
device_broadcasters = {}
# Accumulator to track total messages sent to the frontend
total_messages_sent_to_frontend = 0
# Batch queue for message processing
device_save_queues = {}       # device_id -> asyncio.Queue for saving
device_savers = {}            # device_id -> Task (saving)
device_config = {}            # device_id -> {"save_flag": bool, ... other config ...}

# Batch size and interval settings - optimized for high throughput
BATCH_SIZE = 500  # Reduced batch size for faster processing
BATCH_INTERVAL = 1.0  # Reduced interval for faster processing

async def process_message_batches(msg):
    """Handles incoming MQTT messages, processes them directly."""
    try:
        # Decode the MQTT message payload and parse it into a dictionary
        message_content = json.loads(msg.payload.decode())  # Parse directly
        
        # Process message directly instead of queuing
        device_id = message_content.get("device_id")
        
        if device_id not in device_config:
            device_config[device_id] = {"save_flag": False}
        
        # Ensure broadcaster is started for this device
        await start_device_broadcaster(device_id)
        
        # Put message in device queue for broadcasting
        try:
            device_queues[device_id].put_nowait(message_content)
        except asyncio.QueueFull:
            print(f"Warning: Device queue full for {device_id}")
        
        # Save message if save flag is enabled
        if app.shared_state.save_flag:
            await start_device_saver(device_id)
            try:
                device_save_queues[device_id].put_nowait(message_content)
            except asyncio.QueueFull:
                print(f"Warning: Save queue full for {device_id}")

    except json.JSONDecodeError as e:
        print(f"Error decoding MQTT message: {e}")
    except Exception as e:
        print(f"Error processing MQTT message: {e}")

async def start_device_broadcaster(device_id: str):
    """Starts a broadcaster task for a specific device_id, if not already started."""
    if device_id not in device_queues:
        device_queues[device_id] = asyncio.Queue()

    if device_id not in device_broadcasters:
        # Create the broadcaster task
        device_broadcasters[device_id] = asyncio.create_task(broadcast_messages(device_id))

async def global_message_processor():
    """Efficiently processes messages from the global queue."""
    print("Global message processor started")
    while True:
        try:
            # Process messages in batches for efficiency
            messages = []
            start_time = time.time()
            
            # Collect messages for up to 50ms or until we have 200 messages
            while len(messages) < 200 and (time.time() - start_time) < 0.05:
                try:
                    message = await asyncio.wait_for(global_message_queue.get(), timeout=0.005)
                    messages.append(message)
                except asyncio.TimeoutError:
                    break
            
            if not messages:
                await asyncio.sleep(0.0001)  # Very short sleep if no messages
                continue
            
            # Process all messages in the batch efficiently
            device_batches = {}
            
            for message_content in messages:
                device_id = message_content.get("device_id")
                
                if device_id not in device_config:
                    device_config[device_id] = {"save_flag": False}
                
                # Group messages by device for efficient processing
                if device_id not in device_batches:
                    device_batches[device_id] = []
                device_batches[device_id].append(message_content)
            
            # Process each device's messages
            for device_id, device_messages in device_batches.items():
                # Ensure broadcaster is started for this device
                await start_device_broadcaster(device_id)
                
                # Put all messages for this device in queue
                for message_content in device_messages:
                    try:
                        device_queues[device_id].put_nowait(message_content)
                    except asyncio.QueueFull:
                        print(f"Warning: Device queue full for {device_id}")
                        break
                
                # Save messages if save flag is enabled
                if app.shared_state.save_flag:
                    await start_device_saver(device_id)
                    for message_content in device_messages:
                        try:
                            device_save_queues[device_id].put_nowait(message_content)
                        except asyncio.QueueFull:
                            print(f"Warning: Save queue full for {device_id}")
                            break
                        
        except Exception as e:
            print(f"Error in global message processor: {e}")
            await asyncio.sleep(0.01)

async def start_device_saver(device_id: str):
    """Start a saver task if not started."""
    if device_id not in device_save_queues:
        device_save_queues[device_id] = asyncio.Queue()
    if device_id not in device_savers:
        device_savers[device_id] = asyncio.create_task(batch_processor(device_id))

async def batch_processor(device_id: str, batch_size: int = 500, interval: float = 1.0):
    """
    Continuously consumes messages for a specific device from its dedicated queue,
    batches them, and processes the batches.
    
    :param device_id: ID of the device to process.
    :param batch_size: Maximum number of messages per batch.
    :param interval: Time interval in seconds to wait before processing whatever
                     messages have accumulated even if not at full batch_size.
    """
    queue = device_save_queues[device_id]
    pending_messages = []
    last_flush = asyncio.get_event_loop().time()

    while True:
        try:
            # Wait for a message, or a timeout
            # timeout ensures that we periodically flush even if we don't get a full batch
            message = await asyncio.wait_for(queue.get(), timeout=interval)
            pending_messages.append(message)

            # If we hit the batch size, process the batch
            if len(pending_messages) >= batch_size:
                await process_batch(device_id, pending_messages)
                pending_messages.clear()
                last_flush = asyncio.get_event_loop().time()

        except asyncio.TimeoutError:
            # Interval passed without enough messages to fill a batch
            # Process what we have if there's anything pending
            if pending_messages:
                await process_batch(device_id, pending_messages)
                pending_messages.clear()
                last_flush = asyncio.get_event_loop().time()


async def process_batch(device_id: str, batch: list):
    """
    Processes a batch of messages and saves them to the database.
    """
    try:
        async with get_db() as db:
            # First, ensure the device exists in the iot_devices table
            from app.models import IoTDevice
            from sqlalchemy.future import select
            
            # Check if device exists
            result = await db.execute(
                select(IoTDevice).where(IoTDevice.id == device_id)
            )
            device = result.scalars().first()
            
            if not device:
                print(f"Device {device_id} not found, creating it...")
                # Create the device
                new_device = IoTDevice(
                    id=device_id,
                    device_name=f"Device {device_id}",
                    device_type="sensor",
                    device_token=batch[0].get("device_token", "default_token"),
                    user_id=1  # Default user_id
                )
                db.add(new_device)
                await db.commit()
                print(f"Device {device_id} created successfully")
            
            # Convert messages to records for bulk insert
            records = []
            for msg in batch:
                ts_str = msg["timestamp"].replace("Z", "+00:00")
                timestamp = datetime.fromisoformat(ts_str)

                records.append({
                    "device_id": msg["device_id"],
                    "timestamp": timestamp,
                    "displacement": msg["displacement"],
                    "force": msg["force"]
                })

            # Bulk insert
            await save_device_data_batch(db, records)

        print(f"Batch of {len(batch)} messages for device {device_id} saved successfully.")
    except Exception as e:
        print(f"Error saving batch for device {device_id}: {e}")
        import traceback
        traceback.print_exc()

# async def broadcast_messages():
#     """Batch messages and broadcast them to WebSocket clients."""
#     global total_messages_sent_to_frontend
#     while True:
#         batch = []
#         start_time = time.time()

#         try:
#             while time.time() - start_time < 1:  # Collect for up to 1 second
#                 try:
#                     message = message_queue.get_nowait()
#                     batch.append(message)
#                 except queue.Empty:
#                     await asyncio.sleep(0.01)  # Sleep briefly to avoid busy-waiting

#         except Exception as e:
#             print(f"Error collecting batch: {e}")

#         if batch:
#             print("Sending batch with size:", len(batch))
#             total_messages_sent_to_frontend += len(batch)  # Update the accumulator
#             print(f"Total messages sent to frontend: {total_messages_sent_to_frontend}")
#             await send_to_connected_clients(batch)

async def broadcast_messages(device_id: str):
    """Batch messages and broadcast them to WebSocket clients."""
    global total_messages_sent_to_frontend
    BATCH_SIZE = 2000  # Increased batch size for better throughput
    BATCH_TIMEOUT = 0.05  # Reduced timeout for faster processing
    queue = device_queues[device_id]

    while True:
        batch = []
        start_time = time.time()  # Track the time when batch collection started
        # Collect messages for the batch
        while len(batch) < BATCH_SIZE and (time.time() - start_time) < BATCH_TIMEOUT:
            try:    
                message = await asyncio.wait_for(queue.get(), timeout=0.005)  # Reduced timeout
                batch.append(message)
            except asyncio.TimeoutError:
                await asyncio.sleep(0.0005)  # Reduced sleep time

        # Send the batch if it's non-empty
        if batch:
            print(f"Sending batch with size: {len(batch)}")
            total_messages_sent_to_frontend += len(batch)  # Update the accumulator
            print(f"Total messages sent to frontend: {total_messages_sent_to_frontend}")
            
            # Skip database lookup and websocket processing for now to improve throughput
            # Only process if websockets are actually connected
            websockets = websocket_connections.get("1", set())
            print(f"Checking websockets for client_id '1': {websockets}")
            print(f"All websocket_connections: {websocket_connections}")
            if websockets:
                try:
                    # Quick database lookup without async context manager
                    user_id = "1"  # Hardcode for now to avoid DB lookup
                    await send_to_connected_clients(user_id, batch)
                except Exception as e:
                    print(f"Error in broadcast: {e}")
        else:
            # No messages collected in this cycle, sleep briefly to reduce CPU usage
            await asyncio.sleep(0.005)  # Reduced sleep time


async def send_to_connected_clients(client_id: str, messages: list):
    """Send a batch of messages to all connected WebSocket clients."""
    websockets = websocket_connections.get(client_id, set())
    print(websockets)
    if websockets:
        try:
            message_data = json.dumps(messages)
            tasks = [ws.send_text(message_data) for ws in websockets]
            await asyncio.gather(*tasks)
        except Exception as e:
            print(f"Error broadcasting messages to user {client_id}: {e}")
    else:
        print(f"No active websocket connections found for user {client_id}")


def monitor_message_rate():
    """Monitor messages received per second."""
    while True:
        time.sleep(1)
        # Add logic to track and print the message rate
