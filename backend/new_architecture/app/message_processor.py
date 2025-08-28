import asyncio
import json
import time
import orjson
import zlib
from datetime import datetime
from typing import Dict, Set, List
from fastapi import WebSocket
from app.db import get_db, save_device_data_batch
from app.models import IoTDevice
from app.websocket_manager import websocket_connections  # Import from websocket_manager
from app.shared_state import save_flag  # Import save_flag

# Global variables for device queues
device_queues: Dict[str, asyncio.Queue] = {}
device_config: Dict[str, dict] = {}
device_save_queues: Dict[str, asyncio.Queue] = {}
device_broadcasters: Dict[str, asyncio.Task] = {}  # Track broadcaster tasks
device_savers: Dict[str, asyncio.Task] = {}  # Track saver tasks
global_message_queue: asyncio.Queue = asyncio.Queue()  # Global message queue

# Global counter for total messages sent to frontend
total_messages_sent_to_frontend = 0

# WebSocket broadcasting configuration
WEBSOCKET_BATCH_SIZE = 500  # Smaller batch size for frontend broadcast
WEBSOCKET_BATCH_TIMEOUT = 0.02  # 20ms timeout for frontend batches
COMPRESSION_THRESHOLD = 1000  # Compress if batch size > 1000
COMPRESSION_LEVEL = 6  # zlib compression level (1-9, 6 is balanced)

# Monitoring counters for broadcasting and database operations
class ProcessingCounters:
    def __init__(self):
        self.device_processed = 0
        self.broadcast_sent = 0
        self.broadcast_errors = 0
        self.db_saved = 0
        self.db_errors = 0
        self.start_time = time.time()
    
    def get_stats(self):
        elapsed = time.time() - self.start_time
        return {
            "device_processed": self.device_processed,
            "broadcast_sent": self.broadcast_sent,
            "broadcast_errors": self.broadcast_errors,
            "db_saved": self.db_saved,
            "db_errors": self.db_errors,
            "elapsed_time": elapsed,
            "processing_rate": self.device_processed / elapsed if elapsed > 0 else 0,
            "broadcast_rate": self.broadcast_sent / elapsed if elapsed > 0 else 0,
            "db_rate": self.db_saved / elapsed if elapsed > 0 else 0
        }

# Global processing counters
processing_counters = ProcessingCounters()

# Function to get processing stats
def get_processing_stats():
    """Get current processing statistics."""
    return processing_counters.get_stats()

def print_processing_stats():
    """Print current processing statistics."""
    stats = processing_counters.get_stats()
    print(f"\n📊 PROCESSING STATS:")
    print(f"   Device Processed: {stats['device_processed']} ({stats['processing_rate']:.1f}/sec)")
    print(f"   Broadcast Sent: {stats['broadcast_sent']} ({stats['broadcast_rate']:.1f}/sec)")
    print(f"   Broadcast Errors: {stats['broadcast_errors']}")
    print(f"   DB Saved: {stats['db_saved']} ({stats['db_rate']:.1f}/sec)")
    print(f"   DB Errors: {stats['db_errors']}")
    print(f"   Elapsed Time: {stats['elapsed_time']:.1f} seconds")

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
        if save_flag:
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
                if save_flag:
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

            # Process batch if we have enough messages or enough time has passed
            current_time = asyncio.get_event_loop().time()
            if len(pending_messages) >= batch_size or (current_time - last_flush) >= interval:
                if pending_messages:
                    # MONITORING: Count database saves
                    processing_counters.db_saved += len(pending_messages)
                    
                    await save_device_data_batch_to_db(device_id, pending_messages)
                    pending_messages = []
                    last_flush = current_time

        except asyncio.TimeoutError:
            # Timeout occurred, flush any pending messages
            if pending_messages:
                # MONITORING: Count database saves
                processing_counters.db_saved += len(pending_messages)
                
                await save_device_data_batch_to_db(device_id, pending_messages)
                pending_messages = []
                last_flush = asyncio.get_event_loop().time()
        except Exception as e:
            # MONITORING: Count database errors
            processing_counters.db_errors += len(pending_messages)
            print(f"Error in batch processor for device {device_id}: {e}")
            await asyncio.sleep(0.1)  # Brief pause on error


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
    """Batch messages and broadcast them to WebSocket clients based on device_id."""
    global total_messages_sent_to_frontend
    BATCH_SIZE = 2000  # Backend processing batch size
    BATCH_TIMEOUT = 0.05  # Backend processing timeout
    queue = device_queues[device_id]

    # Device to frontend mapping
    device_to_frontend = {
        "frontend1_device": "1",
        "frontend1_high_perf_device": "1", 
        "frontend1_ultra_high_perf_device": "1",  # New optimized publisher
        "frontend2_device": "2",
        "frontend2_high_perf_device": "2",
        "frontend2_ultra_high_perf_device": "2"   # New optimized publisher
    }
    
    # Get the target frontend for this device
    target_frontend = device_to_frontend.get(device_id, "1")  # Default to frontend-1 if unknown
    
    print(f"🔀 Device {device_id} mapped to frontend-{target_frontend}")

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
            # MONITORING: Count device processed messages
            processing_counters.device_processed += len(batch)
            
            print(f"📤 Sending batch of {len(batch)} messages from {device_id} to frontend-{target_frontend}")
            total_messages_sent_to_frontend += len(batch)  # Update the accumulator
            print(f"📊 Total messages sent to frontend: {total_messages_sent_to_frontend}")
            
            # Send only to the target frontend
            websockets = websocket_connections.get(target_frontend, set())
            print(f"🔍 Checking websockets for frontend-{target_frontend}: {len(websockets)} connections")
            if websockets:
                try:
                    await send_to_connected_clients_optimized(target_frontend, batch)
                    # MONITORING: Count successful broadcasts
                    processing_counters.broadcast_sent += len(batch)
                    print(f"✅ Successfully sent {len(batch)} messages to frontend-{target_frontend}")
                except Exception as e:
                    # MONITORING: Count broadcast errors
                    processing_counters.broadcast_errors += len(batch)
                    print(f"❌ Error sending to frontend-{target_frontend}: {e}")
            else:
                print(f"⚠️  No WebSocket connections found for frontend-{target_frontend}")
        else:
            # No messages collected in this cycle, sleep briefly to reduce CPU usage
            await asyncio.sleep(0.005)  # Reduced sleep time


async def send_to_connected_clients_optimized(client_id: str, messages: list):
    """Send a batch of messages to all connected WebSocket clients with optimizations."""
    websockets = websocket_connections.get(client_id, set())
    if not websockets:
        print(f"No active websocket connections found for user {client_id}")
        return

    try:
        # OPTIMIZED: Use orjson for faster serialization and binary output
        message_data = orjson.dumps(messages)
        
        # OPTIMIZED: Compress large payloads to reduce network overhead
        if len(message_data) > COMPRESSION_THRESHOLD:
            compressed_data = zlib.compress(message_data, level=COMPRESSION_LEVEL)
            print(f"📦 Compressed payload: {len(message_data)} -> {len(compressed_data)} bytes ({len(compressed_data)/len(message_data)*100:.1f}% compression)")
            
            # Send compressed data as binary
            tasks = [ws.send_bytes(compressed_data) for ws in websockets]
        else:
            # Send uncompressed data as binary (faster than text)
            tasks = [ws.send_bytes(message_data) for ws in websockets]
        
        # OPTIMIZED: Use gather for concurrent sending
        await asyncio.gather(*tasks, return_exceptions=True)
        
    except Exception as e:
        print(f"Error broadcasting messages to user {client_id}: {e}")


async def send_to_connected_clients(client_id: str, messages: list):
    """Legacy method - kept for backward compatibility."""
    await send_to_connected_clients_optimized(client_id, messages)


def monitor_message_rate():
    """Monitor messages received per second."""
    while True:
        time.sleep(1)
        # Add logic to track and print the message rate
