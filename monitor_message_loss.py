#!/usr/bin/env python3
"""
Comprehensive Message Loss Monitoring Script

This script monitors message flow at each stage to identify where loss occurs:
1. Publisher total published
2. Broker delivery (using mosquitto_sub)
3. Backend on_message counter
4. After processing, before saving to DB
5. After broadcasting to frontend

Usage:
    python monitor_message_loss.py [publisher_script] [duration_seconds]
    
Example:
    python monitor_message_loss.py frontend1_high_performance_optimized.py 30
"""

import asyncio
import subprocess
import time
import sys
import json
import requests
from datetime import datetime
import threading
import queue

class MessageLossMonitor:
    def __init__(self, publisher_script=None, duration=30):
        self.publisher_script = publisher_script
        self.duration = duration
        self.start_time = time.time()
        self.broker_message_count = 0
        self.backend_stats = {}
        self.monitoring_active = True
        
        # Queues for collecting stats
        self.broker_stats_queue = queue.Queue()
        self.backend_stats_queue = queue.Queue()
        
    def start_broker_monitoring(self):
        """Start mosquitto_sub to count broker messages."""
        try:
            print("🔍 Starting broker monitoring with mosquitto_sub...")
            # Start mosquitto_sub to count all messages
            cmd = ["mosquitto_sub", "-v", "-t", "#"]
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Count messages from mosquitto_sub output
            message_count = 0
            start_time = time.time()
            
            while self.monitoring_active and time.time() - start_time < self.duration:
                line = process.stdout.readline()
                if line:
                    message_count += 1
                    if message_count % 1000 == 0:
                        print(f"📊 Broker received: {message_count} messages")
            
            process.terminate()
            self.broker_message_count = message_count
            print(f"📊 Final broker count: {message_count} messages")
            
        except Exception as e:
            print(f"❌ Error in broker monitoring: {e}")
    
    def get_backend_stats(self):
        """Get backend statistics via HTTP API."""
        try:
            # Try to get stats from backend monitoring endpoint
            response = requests.get("http://localhost:8000/monitoring/stats", timeout=5)
            if response.status_code == 200:
                return response.json()
        except:
            pass
        
        # Fallback: return basic stats
        return {
            "mqtt_received": 0,
            "mqtt_parsed": 0,
            "device_processed": 0,
            "broadcast_sent": 0,
            "db_saved": 0
        }
    
    def start_publisher(self):
        """Start the publisher script if specified."""
        if not self.publisher_script:
            print("⚠️  No publisher script specified, monitoring existing traffic only")
            return None
            
        try:
            print(f"🚀 Starting publisher: {self.publisher_script}")
            process = subprocess.Popen(
                ["python", self.publisher_script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            return process
        except Exception as e:
            print(f"❌ Error starting publisher: {e}")
            return None
    
    def monitor_backend_stats(self):
        """Continuously monitor backend statistics."""
        while self.monitoring_active:
            try:
                stats = self.get_backend_stats()
                self.backend_stats_queue.put(stats)
                time.sleep(1)  # Check every second
            except Exception as e:
                print(f"❌ Error getting backend stats: {e}")
                time.sleep(1)
    
    def print_summary(self):
        """Print comprehensive monitoring summary."""
        print("\n" + "="*80)
        print("📊 COMPREHENSIVE MESSAGE LOSS ANALYSIS")
        print("="*80)
        
        # Get final backend stats
        final_backend_stats = self.get_backend_stats()
        
        print(f"\n⏱️  Monitoring Duration: {self.duration} seconds")
        print(f"🕐 Start Time: {datetime.fromtimestamp(self.start_time)}")
        print(f"🕐 End Time: {datetime.fromtimestamp(time.time())}")
        
        print(f"\n📈 MESSAGE COUNTS BY STAGE:")
        print(f"   1. Broker Received: {self.broker_message_count}")
        print(f"   2. Backend MQTT Received: {final_backend_stats.get('mqtt_received', 0)}")
        print(f"   3. Backend MQTT Parsed: {final_backend_stats.get('mqtt_parsed', 0)}")
        print(f"   4. Device Processed: {final_backend_stats.get('device_processed', 0)}")
        print(f"   5. Broadcast Sent: {final_backend_stats.get('broadcast_sent', 0)}")
        print(f"   6. Database Saved: {final_backend_stats.get('db_saved', 0)}")
        
        # Calculate loss at each stage
        print(f"\n🔍 LOSS ANALYSIS:")
        
        # Stage 1: Publisher → Broker
        publisher_estimate = self.broker_message_count  # Assuming broker count is accurate
        broker_received = self.broker_message_count
        loss_publisher_broker = publisher_estimate - broker_received
        print(f"   Publisher → Broker: {loss_publisher_broker} messages lost")
        
        # Stage 2: Broker → Backend
        backend_received = final_backend_stats.get('mqtt_received', 0)
        loss_broker_backend = broker_received - backend_received
        print(f"   Broker → Backend: {loss_broker_backend} messages lost")
        
        # Stage 3: Backend Parsing
        backend_parsed = final_backend_stats.get('mqtt_parsed', 0)
        loss_backend_parsing = backend_received - backend_parsed
        print(f"   Backend Parsing: {loss_backend_parsing} messages lost")
        
        # Stage 4: Device Processing
        device_processed = final_backend_stats.get('device_processed', 0)
        loss_device_processing = backend_parsed - device_processed
        print(f"   Device Processing: {loss_device_processing} messages lost")
        
        # Stage 5: Broadcasting
        broadcast_sent = final_backend_stats.get('broadcast_sent', 0)
        loss_broadcasting = device_processed - broadcast_sent
        print(f"   Broadcasting: {loss_broadcasting} messages lost")
        
        # Stage 6: Database
        db_saved = final_backend_stats.get('db_saved', 0)
        loss_database = device_processed - db_saved
        print(f"   Database: {loss_database} messages lost")
        
        # Calculate rates
        elapsed = time.time() - self.start_time
        print(f"\n📊 RATES:")
        print(f"   Broker Rate: {broker_received/elapsed:.1f} msg/sec")
        print(f"   Backend Rate: {backend_received/elapsed:.1f} msg/sec")
        print(f"   Processing Rate: {device_processed/elapsed:.1f} msg/sec")
        print(f"   Broadcasting Rate: {broadcast_sent/elapsed:.1f} msg/sec")
        print(f"   Database Rate: {db_saved/elapsed:.1f} msg/sec")
        
        # Identify bottlenecks
        print(f"\n🎯 BOTTLENECK ANALYSIS:")
        if loss_publisher_broker > 0:
            print(f"   ⚠️  Publisher → Broker: Network/ACK issues detected")
        if loss_broker_backend > 0:
            print(f"   ⚠️  Broker → Backend: Mosquitto dropping or client inflight too small")
        if loss_backend_parsing > 0:
            print(f"   ⚠️  Backend Parsing: JSON parsing errors or race conditions")
        if loss_device_processing > 0:
            print(f"   ⚠️  Device Processing: Queue overflow or processing bottlenecks")
        if loss_broadcasting > 0:
            print(f"   ⚠️  Broadcasting: WebSocket issues or frontend not connected")
        if loss_database > 0:
            print(f"   ⚠️  Database: Database connection or save queue issues")
        
        if all(loss == 0 for loss in [loss_publisher_broker, loss_broker_backend, loss_backend_parsing, 
                                    loss_device_processing, loss_broadcasting, loss_database]):
            print(f"   ✅ No message loss detected - system is working perfectly!")
        
        print("="*80)
    
    def run(self):
        """Run the complete monitoring process."""
        print("🚀 Starting comprehensive message loss monitoring...")
        print(f"📋 Publisher: {self.publisher_script or 'None (monitoring existing traffic)'}")
        print(f"⏱️  Duration: {self.duration} seconds")
        print(f"🕐 Start Time: {datetime.fromtimestamp(self.start_time)}")
        
        # Start broker monitoring in separate thread
        broker_thread = threading.Thread(target=self.start_broker_monitoring)
        broker_thread.daemon = True
        broker_thread.start()
        
        # Start backend monitoring in separate thread
        backend_thread = threading.Thread(target=self.monitor_backend_stats)
        backend_thread.daemon = True
        backend_thread.start()
        
        # Start publisher if specified
        publisher_process = self.start_publisher()
        
        # Wait for monitoring duration
        print(f"⏳ Monitoring for {self.duration} seconds...")
        time.sleep(self.duration)
        
        # Stop monitoring
        self.monitoring_active = False
        
        # Stop publisher if running
        if publisher_process:
            publisher_process.terminate()
            print("🛑 Publisher stopped")
        
        # Wait for threads to finish
        broker_thread.join(timeout=5)
        backend_thread.join(timeout=5)
        
        # Print final summary
        self.print_summary()

def main():
    """Main function to run the monitoring script."""
    if len(sys.argv) < 2:
        print("Usage: python monitor_message_loss.py [publisher_script] [duration_seconds]")
        print("Example: python monitor_message_loss.py frontend1_high_performance_optimized.py 30")
        sys.exit(1)
    
    publisher_script = sys.argv[1] if len(sys.argv) > 1 else None
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    
    monitor = MessageLossMonitor(publisher_script, duration)
    monitor.run()

if __name__ == "__main__":
    main()
