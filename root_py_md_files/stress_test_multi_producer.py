import asyncio
import time
import threading
import queue
import orjson
import os
import concurrent.futures as futures
import paho.mqtt.client as mqtt
from datetime import datetime
import random

# Test Configuration
TOTAL_MSGS_PER_PRODUCER = 5000
NUM_PRODUCERS = 3
DEVICE_IDS = ["device_001", "device_002", "device_003", "device_004", "device_005"]
RAW_Q = queue.SimpleQueue()  # unbounded, no drops
received = 0
processed = 0
recv_lock = threading.Lock()
device_stats = {device_id: {"received": 0, "processed": 0} for device_id in DEVICE_IDS}

# ---- MQTT Subscriber (simulating our backend) ----
def on_connect_sub(client, userdata, flags, rc):
    if rc == 0:
        print("Subscriber connected")
        client.subscribe("MON", qos=1)
    else:
        print("Connect failed:", rc)

def on_message_sub(client, userdata, msg):
    global received
    RAW_Q.put(msg.payload)  # push raw bytes; no parsing here
    with recv_lock:
        received += 1

def start_subscriber():
    c = mqtt.Client(client_id="stress_test_sub", clean_session=False)
    c.on_connect = on_connect_sub
    c.on_message = on_message_sub
    c.max_inflight_messages_set(10000)
    c.max_queued_messages_set(100000)
    c.connect("127.0.0.1", 1883, keepalive=60)
    c.loop_start()
    return c

# ---- Multiple Publishers ----
def generate_displacement(index):
    min_val = -1.2168244889861554e-6
    max_val = -3.203646967473276e-8
    scale = (max_val - min_val) / 2
    offset = (max_val + min_val) / 2
    return offset + scale * (index % 360)

def generate_force(index):
    base = 5e-12 * (index % 100)
    noise = random.uniform(-5e-13, 5e-13)
    return base + noise

def publisher(producer_id, device_id, messages_per_second, total_messages):
    """Individual publisher for a specific device"""
    pub = mqtt.Client(client_id=f"producer_{producer_id}_{device_id}", clean_session=False)
    pub.connect("127.0.0.1", 1883, keepalive=60)
    pub.loop_start()
    
    print(f"Producer {producer_id} (Device {device_id}) starting - {messages_per_second} msgs/sec, {total_messages} total")
    
    for i in range(total_messages):
        msg = {
            "device_id": device_id,
            "device_token": f"token_{device_id}",
            "ts_ms": int(time.time() * 1000),
            "timestamp": datetime.now().isoformat(),
            "displacement": generate_displacement(i),
            "force": generate_force(i),
            "producer_id": producer_id,
            "message_id": i
        }
        pub.publish("MON", orjson.dumps(msg), qos=1)
        
        # Rate limiting
        if messages_per_second > 0:
            time.sleep(1.0 / messages_per_second)
    
    pub.loop_stop()
    pub.disconnect()
    print(f"Producer {producer_id} (Device {device_id}) finished")

def start_multiple_publishers():
    """Start multiple publishers with different rates and device IDs"""
    threads = []
    
    # Create publishers with different rates and device IDs
    rates = [2000, 1500, 1000]  # Different rates for stress testing
    
    for i in range(NUM_PRODUCERS):
        device_id = DEVICE_IDS[i % len(DEVICE_IDS)]
        rate = rates[i % len(rates)]
        
        thread = threading.Thread(
            target=publisher,
            args=(i + 1, device_id, rate, TOTAL_MSGS_PER_PRODUCER),
            daemon=True
        )
        threads.append(thread)
        thread.start()
    
    return threads

# ---- Processing (simulating our backend processing) ----
def process_batch_sync(batch_dicts):
    """Simulate CPU-intensive processing"""
    # Simulate some work
    time.sleep(0.001)  # 1ms of work
    return len(batch_dicts)

async def drain_decode_and_process():
    """Main processing loop - simulates our optimized backend"""
    global processed
    
    # Use CPU-scaled thread pool
    EXEC = futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4)
    loop = asyncio.get_running_loop()
    
    # Device-specific queues (simulating our device_queues)
    device_queues = {device_id: asyncio.Queue() for device_id in DEVICE_IDS}
    
    last_log = time.time()
    total_expected = NUM_PRODUCERS * TOTAL_MSGS_PER_PRODUCER
    
    while True:
        # Collect a chunk (fast)
        chunk = []
        t0 = time.time()
        while len(chunk) < 1000 and (time.time() - t0) < 0.01:  # 10ms collection window
            try:
                chunk.append(RAW_Q.get_nowait())
            except queue.Empty:
                break
        
        if not chunk:
            await asyncio.sleep(0.001)
        else:
            # Decode with orjson (fast)
            batch = []
            for raw_payload in chunk:
                try:
                    msg = orjson.loads(raw_payload)
                    batch.append(msg)
                except Exception as e:
                    print(f"Error parsing message: {e}")
                    continue
            
            # Group by device (simulating our device grouping)
            device_batches = {}
            for msg in batch:
                device_id = msg.get("device_id")
                if device_id in DEVICE_IDS:
                    if device_id not in device_batches:
                        device_batches[device_id] = []
                    device_batches[device_id].append(msg)
            
            # Process each device's batch in parallel
            tasks = []
            for device_id, device_messages in device_batches.items():
                # Put in device queue (simulating our device_queues)
                for msg in device_messages:
                    try:
                        device_queues[device_id].put_nowait(msg)
                    except asyncio.QueueFull:
                        print(f"Device queue full for {device_id}")
                        break
                
                # Process batch in thread pool (simulating our parallel processing)
                if device_messages:
                    task = loop.run_in_executor(EXEC, process_batch_sync, device_messages)
                    tasks.append(task)
            
            # Wait for all processing to complete
            if tasks:
                results = await asyncio.gather(*tasks)
                processed += sum(results)
                
                # Update device stats
                for device_id, device_messages in device_batches.items():
                    device_stats[device_id]["processed"] += len(device_messages)
        
        # Stop condition
        with recv_lock:
            rec = received
        if rec >= total_expected and RAW_Q.empty():
            if time.time() - last_log > 0.5:
                print(f"Draining complete: received={rec}, processed={processed}")
            if processed >= rec:
                EXEC.shutdown(wait=True, cancel_futures=False)
                break
        
        # Periodic stats
        if time.time() - last_log > 2.0:
            with recv_lock:
                rec = received
            print(f"\n=== STATUS UPDATE ===")
            print(f"Total: recv={rec}/{total_expected}, proc={processed}")
            print(f"Queue size: {getattr(RAW_Q, 'qsize', lambda: -1)() if hasattr(RAW_Q, 'qsize') else 'n/a'}")
            print(f"Device stats:")
            for device_id, stats in device_stats.items():
                print(f"  {device_id}: recv={stats['received']}, proc={stats['processed']}")
            print(f"===================\n")
            last_log = time.time()

async def main():
    print(f"=== STRESS TEST: {NUM_PRODUCERS} Producers, {TOTAL_MSGS_PER_PRODUCER} msgs each ===")
    print(f"Total expected messages: {NUM_PRODUCERS * TOTAL_MSGS_PER_PRODUCER}")
    print(f"Device IDs: {DEVICE_IDS}")
    print(f"CPU cores: {os.cpu_count()}")
    print("=" * 60)
    
    # Start subscriber
    sub = start_subscriber()
    
    # Start multiple publishers
    pub_threads = start_multiple_publishers()
    
    # Start processing
    start_time = time.time()
    await drain_decode_and_process()
    end_time = time.time()
    
    # Cleanup
    sub.loop_stop()
    sub.disconnect()
    
    # Wait for publishers to finish
    for thread in pub_threads:
        thread.join()
    
    # Final results
    duration = end_time - start_time
    total_messages = NUM_PRODUCERS * TOTAL_MSGS_PER_PRODUCER
    throughput = total_messages / duration if duration > 0 else 0
    
    print(f"\n=== FINAL RESULTS ===")
    print(f"Duration: {duration:.2f} seconds")
    print(f"Total messages: {total_messages}")
    print(f"Throughput: {throughput:.2f} messages/second")
    print(f"Received: {received}")
    print(f"Processed: {processed}")
    print(f"Success rate: {(processed/total_messages)*100:.2f}%")
    print(f"Device breakdown:")
    for device_id, stats in device_stats.items():
        success_rate = (stats['processed']/stats['received'])*100 if stats['received'] > 0 else 0
        print(f"  {device_id}: {stats['received']}/{stats['processed']} ({success_rate:.2f}%)")
    print("=" * 20)

if __name__ == "__main__":
    asyncio.run(main())
