#!/usr/bin/env python3
"""
Frontend-2 Ultra High Performance Optimized Publisher
Advanced optimizations for maximum throughput:
- QoS 0 for maximum speed
- Batched messages (1000 points per MQTT message)
- orjson for fastest serialization
- Optimized MQTT client settings
- Single socket reuse
"""

import paho.mqtt.client as mqtt
import orjson
import time
import random
import threading
from datetime import datetime

# MQTT Configuration
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
BASE_TOPIC = "device_data"

class UltraHighPerformancePublisher:
    def __init__(self):
        # Optimized MQTT client settings
        self.client = mqtt.Client(
            client_id="frontend2_ultra_high_perf_publisher", 
            protocol=mqtt.MQTTv311, 
            clean_session=False
        )
        
        # Ultra-high performance settings
        self.device_id = "frontend2_ultra_high_perf_device"
        self.message_count = 0
        self.is_running = False
        self.target_rate = 10000  # 10,000 messages per second
        self.total_messages = 100000  # 100,000 total messages
        self.batch_size = 1000  # 1000 points per MQTT message
        self.mqtt_messages = 0  # Count of actual MQTT messages sent
        
        # Device-specific topic for optimization
        self.topic = f"{BASE_TOPIC}/{self.device_id}"
        
        # Performance tracking
        self.start_time = None
        self.last_report_time = 0
        self.report_interval = 1.0  # Report every second
        
        # Set up callbacks
        self.client.on_connect = self.on_connect
        self.client.on_publish = self.on_publish
        self.client.on_disconnect = self.on_disconnect
        
        # Optimize MQTT client for maximum throughput
        self.client.max_inflight_messages_set(50000)  # Very high inflight limit
        self.client.max_queued_messages_set(1000000)  # Very high queue limit
        
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"✅ Frontend-2 Ultra High Performance Publisher connected to MQTT broker")
            print(f"📊 Configuration:")
            print(f"   - Device ID: {self.device_id}")
            print(f"   - Target Rate: {self.target_rate:,} msg/sec")
            print(f"   - Total Messages: {self.total_messages:,}")
            print(f"   - Batch Size: {self.batch_size:,} points per MQTT message")
            print(f"   - QoS Level: 0 (maximum throughput)")
            print(f"   - Topic: {self.topic}")
            print(f"   - Max Inflight: 50,000")
            print(f"   - Max Queued: 1,000,000")
            print(f"🚀 Starting ultra-high-performance data transmission...")
        else:
            print(f"❌ Connection failed with code {rc}")
            
    def on_publish(self, client, userdata, mid):
        self.mqtt_messages += 1
        
        # Performance reporting
        current_time = time.time()
        if current_time - self.last_report_time >= self.report_interval:
            elapsed = current_time - self.start_time
            rate = self.message_count / elapsed if elapsed > 0 else 0
            mqtt_rate = self.mqtt_messages / elapsed if elapsed > 0 else 0
            progress = (self.message_count / self.total_messages) * 100
            print(f"📤 Progress: {self.message_count:,}/{self.total_messages:,} ({progress:.1f}%) - Rate: {rate:,.0f} msg/sec (MQTT: {mqtt_rate:.1f}/sec)")
            self.last_report_time = current_time
            
    def on_disconnect(self, client, userdata, rc):
        print(f"🔌 Frontend-2 Ultra High Performance Publisher disconnected")
        
    def generate_data_batch(self, batch_start, batch_end):
        """Generate a batch of data points"""
        batch_data = []
        for i in range(batch_start, batch_end):
            if i >= self.total_messages:
                break
                
            timestamp = datetime.utcnow().isoformat()
            
            # Generate realistic displacement and force values (different from frontend-1)
            base_displacement = 15.0 + (i * 0.001)  # Different base value
            noise_displacement = random.uniform(-2.0, 2.0)  # Different noise range
            displacement = base_displacement + noise_displacement
            
            # Force correlates with displacement (different scaling)
            base_force = displacement * 3.0 + random.uniform(-2, 2)  # Different scaling
            force = max(0, base_force)
            
            data_point = {
                "device_id": self.device_id,
                "timestamp": timestamp,
                "displacement": round(displacement, 3),
                "force": round(force, 3),
                "message_id": i + 1,
                "publisher": "frontend2_ultra_high_perf_publisher",
                "batch_id": batch_start // self.batch_size
            }
            batch_data.append(data_point)
            
        return batch_data
        
    def publish_data(self):
        """Publish data with ultra-high performance optimizations"""
        self.start_time = time.time()
        self.last_report_time = self.start_time
        self.is_running = True
        
        print(f"🚀 Starting ultra-high-performance publishing...")
        print(f"📊 Target: {self.target_rate:,} msg/sec for {self.total_messages:,} messages")
        print(f"📊 Batch Strategy: {self.batch_size:,} points per MQTT message")
        print(f"📊 Expected MQTT Messages: {self.total_messages // self.batch_size:,}")
        
        # Calculate timing for target rate
        points_per_second = self.target_rate
        batches_per_second = points_per_second / self.batch_size
        batch_interval = 1.0 / batches_per_second
        
        print(f"📊 Batch Configuration:")
        print(f"   - Points per batch: {self.batch_size:,}")
        print(f"   - Batches per second: {batches_per_second:.1f}")
        print(f"   - Batch interval: {batch_interval:.3f} seconds")
        
        batch_count = 0
        points_sent = 0
        
        while self.is_running and points_sent < self.total_messages:
            batch_start = batch_count * self.batch_size
            batch_end = batch_start + self.batch_size
            
            if batch_start >= self.total_messages:
                break
                
            # Generate and publish batch
            batch_data = self.generate_data_batch(batch_start, batch_end)
            if batch_data:
                # Serialize entire batch with orjson (fastest)
                payload = orjson.dumps(batch_data)
                
                # Publish with QoS 0 for maximum throughput
                self.client.publish(self.topic, payload, qos=0, retain=False)
                
                points_sent += len(batch_data)
                self.message_count = points_sent
                
                # Wait for next batch
                time.sleep(batch_interval)
                batch_count += 1
            else:
                break
                
        # Final statistics
        elapsed = time.time() - self.start_time
        avg_rate = self.message_count / elapsed if elapsed > 0 else 0
        mqtt_rate = self.mqtt_messages / elapsed if elapsed > 0 else 0
        
        print(f"\n📊 Frontend-2 Ultra High Performance Publisher Statistics:")
        print(f"   - Total Points Sent: {self.message_count:,}")
        print(f"   - Total MQTT Messages: {self.mqtt_messages:,}")
        print(f"   - Total Time: {elapsed:.2f} seconds")
        print(f"   - Average Point Rate: {avg_rate:,.0f} points/sec")
        print(f"   - Average MQTT Rate: {mqtt_rate:.1f} messages/sec")
        print(f"   - Target Rate: {self.target_rate:,} points/sec")
        print(f"   - Performance: {(avg_rate/self.target_rate)*100:.1f}% of target")
        print(f"   - Efficiency: {self.message_count/self.mqtt_messages:.1f} points per MQTT message")
        print(f"   - Topic Used: {self.topic}")
        print(f"   - QoS Level: 0 (maximum throughput)")
        
        # Disconnect
        self.client.disconnect()
        
    def start(self):
        """Start the ultra-high-performance publisher"""
        try:
            # Connect to MQTT broker
            print(f"🔗 Connecting to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}...")
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            
            # Start publishing in a separate thread
            publish_thread = threading.Thread(target=self.publish_data)
            publish_thread.daemon = True
            publish_thread.start()
            
            # Start the MQTT loop
            self.client.loop_forever()
            
        except KeyboardInterrupt:
            print(f"\n⏹️  Stopping Frontend-2 Ultra High Performance Publisher...")
            self.is_running = False
            self.client.disconnect()
        except Exception as e:
            print(f"❌ Error: {e}")
            self.client.disconnect()

def main():
    """Main function to run the Ultra High Performance Publisher"""
    print("=" * 80)
    print("🚀 Frontend-2 Ultra High Performance Optimized Publisher")
    print("=" * 80)
    print("Advanced optimizations for maximum throughput:")
    print("- QoS 0 for maximum speed")
    print("- Batched messages (1000 points per MQTT message)")
    print("- orjson for fastest serialization")
    print("- Optimized MQTT client settings")
    print("- Single socket reuse")
    print("=" * 80)
    print("Make sure:")
    print("1. MQTT broker (mosquitto) is running")
    print("2. Backend is running on port 8000")
    print("3. frontend-2 React app is running on port 3002")
    print("4. System can handle ultra-high message rates")
    print("=" * 80)
    
    publisher = UltraHighPerformancePublisher()
    publisher.start()

if __name__ == "__main__":
    main()
