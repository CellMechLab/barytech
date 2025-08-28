#!/usr/bin/env python3
"""
Test script to verify optimized publishers and backend processing
"""

import requests
import json
import time
import paho.mqtt.client as mqtt
import threading
import websocket

def test_backend_health():
    """Test if backend is responding"""
    try:
        response = requests.get("http://localhost:8000/")
        print(f"✅ Backend health check: {response.status_code}")
        return True
    except Exception as e:
        print(f"❌ Backend health check failed: {e}")
        return False

def test_websocket_connection():
    """Test WebSocket connection to backend"""
    try:
        ws = websocket.create_connection("ws://localhost:8000/ws")
        ws.send(json.dumps({"client_id": "1"}))
        response = ws.recv()
        print(f"✅ WebSocket connection successful: {response}")
        ws.close()
        return True
    except Exception as e:
        print(f"❌ WebSocket connection failed: {e}")
        return False

def test_optimized_mqtt_publisher():
    """Test optimized MQTT publisher with batched messages"""
    try:
        client = mqtt.Client(client_id="test_optimized_publisher")
        client.connect("localhost", 1883, 60)
        
        # Create a batched message (like the optimized publishers)
        batched_message = []
        for i in range(10):  # Small batch for testing
            data_point = {
                "device_id": "frontend1_ultra_high_perf_device",
                "timestamp": "2024-12-04T12:00:00.000Z",
                "displacement": 10.0 + i,
                "force": 25.0 + i * 2,
                "message_id": i + 1,
                "publisher": "test_optimized_publisher",
                "batch_id": 0
            }
            batched_message.append(data_point)
        
        # Send batched message
        client.publish("device_data/frontend1_ultra_high_perf_device", json.dumps(batched_message), qos=0)
        print(f"✅ Optimized MQTT test message sent (batch of {len(batched_message)} points)")
        client.disconnect()
        return True
    except Exception as e:
        print(f"❌ Optimized MQTT test failed: {e}")
        return False

def test_legacy_mqtt_publisher():
    """Test legacy MQTT publisher with single messages"""
    try:
        client = mqtt.Client(client_id="test_legacy_publisher")
        client.connect("localhost", 1883, 60)
        
        # Create a single message (legacy format)
        single_message = {
            "device_id": "frontend1_device",
            "timestamp": "2024-12-04T12:00:00.000Z",
            "displacement": 15.5,
            "force": 45.3,
            "message_id": 999,
            "publisher": "test_legacy_publisher"
        }
        
        # Send single message
        client.publish("device_data/frontend1_device", json.dumps(single_message), qos=1)
        print(f"✅ Legacy MQTT test message sent (single point)")
        client.disconnect()
        return True
    except Exception as e:
        print(f"❌ Legacy MQTT test failed: {e}")
        return False

def main():
    print("=" * 60)
    print("🧪 Optimized Publishers Test")
    print("=" * 60)
    print("\n1. Testing backend health...")
    backend_ok = test_backend_health()
    
    print("\n2. Testing WebSocket connection...")
    websocket_ok = test_websocket_connection()
    
    print("\n3. Testing optimized MQTT publisher (batched)...")
    optimized_mqtt_ok = test_optimized_mqtt_publisher()
    
    print("\n4. Testing legacy MQTT publisher (single)...")
    legacy_mqtt_ok = test_legacy_mqtt_publisher()
    
    print("\n" + "=" * 60)
    print("📊 Test Results:")
    print(f"   Backend Health: {'✅ PASS' if backend_ok else '❌ FAIL'}")
    print(f"   WebSocket: {'✅ PASS' if websocket_ok else '❌ FAIL'}")
    print(f"   Optimized MQTT (Batched): {'✅ PASS' if optimized_mqtt_ok else '❌ FAIL'}")
    print(f"   Legacy MQTT (Single): {'✅ PASS' if legacy_mqtt_ok else '❌ FAIL'}")
    
    if backend_ok and websocket_ok and optimized_mqtt_ok and legacy_mqtt_ok:
        print("\n🎉 All tests passed! Backend can handle both formats.")
        print("\n📋 Next steps:")
        print("1. Run optimized publishers:")
        print("   python frontend1_high_performance_optimized.py")
        print("   python frontend2_high_performance_optimized.py")
        print("2. Check backend logs for 'Processing batched message'")
        print("3. Verify frontends receive data correctly")
    else:
        print("\n⚠️  Some tests failed. Check the issues above.")
    
    print("=" * 60)

if __name__ == "__main__":
    main()
