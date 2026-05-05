#!/usr/bin/env python3
"""
Simple test script to verify monitoring functionality
"""

import requests
import time
import json

def test_monitoring_endpoints():
    """Test the monitoring endpoints."""
    base_url = "http://localhost:8000"
    
    print("🧪 Testing monitoring endpoints...")
    
    # Test stats endpoint
    try:
        response = requests.get(f"{base_url}/monitoring/stats", timeout=5)
        if response.status_code == 200:
            stats = response.json()
            print("✅ Stats endpoint working:")
            print(f"   MQTT Received: {stats.get('mqtt_received', 0)}")
            print(f"   MQTT Parsed: {stats.get('mqtt_parsed', 0)}")
            print(f"   Device Processed: {stats.get('device_processed', 0)}")
            print(f"   Broadcast Sent: {stats.get('broadcast_sent', 0)}")
            print(f"   DB Saved: {stats.get('db_saved', 0)}")
        else:
            print(f"❌ Stats endpoint failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Stats endpoint error: {e}")
    
    # Test health endpoint
    try:
        response = requests.get(f"{base_url}/monitoring/health", timeout=5)
        if response.status_code == 200:
            health = response.json()
            print("✅ Health endpoint working:")
            print(f"   Status: {health.get('status', 'unknown')}")
            print(f"   Parsing Success Rate: {health.get('parsing_success_rate', 0)}%")
            print(f"   Processing Success Rate: {health.get('processing_success_rate', 0)}%")
            print(f"   Broadcast Success Rate: {health.get('broadcast_success_rate', 0)}%")
        else:
            print(f"❌ Health endpoint failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Health endpoint error: {e}")

def monitor_live_stats(duration=30):
    """Monitor live stats for a specified duration."""
    base_url = "http://localhost:8000"
    
    print(f"📊 Monitoring live stats for {duration} seconds...")
    start_time = time.time()
    
    while time.time() - start_time < duration:
        try:
            response = requests.get(f"{base_url}/monitoring/stats", timeout=5)
            if response.status_code == 200:
                stats = response.json()
                elapsed = time.time() - start_time
                
                print(f"\n⏱️  {elapsed:.1f}s - Stats:")
                print(f"   MQTT: {stats.get('mqtt_received', 0)} received, {stats.get('mqtt_rate', 0):.1f}/sec")
                print(f"   Processing: {stats.get('device_processed', 0)} processed, {stats.get('processing_rate', 0):.1f}/sec")
                print(f"   Broadcasting: {stats.get('broadcast_sent', 0)} sent, {stats.get('broadcast_rate', 0):.1f}/sec")
                print(f"   Database: {stats.get('db_saved', 0)} saved, {stats.get('db_rate', 0):.1f}/sec")
            
        except Exception as e:
            print(f"❌ Error getting stats: {e}")
        
        time.sleep(5)  # Check every 5 seconds

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "live":
        duration = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        monitor_live_stats(duration)
    else:
        test_monitoring_endpoints()
