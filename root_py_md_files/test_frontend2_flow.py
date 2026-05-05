#!/usr/bin/env python3
"""
Test script to verify the complete data flow for frontend-2
"""

import requests
import json
import time
import paho.mqtt.client as mqtt
import threading

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
    import websocket
    
    try:
        ws = websocket.create_connection("ws://localhost:8000/ws")
        
        # Send client_id
        ws.send(json.dumps({"client_id": "2"}))
        
        # Wait for response
        response = ws.recv()
        print(f"✅ WebSocket connection successful: {response}")
        
        ws.close()
        return True
    except Exception as e:
        print(f"❌ WebSocket connection failed: {e}")
        return False

def test_mqtt_publisher():
    """Test MQTT publisher"""
    try:
        client = mqtt.Client(client_id="test_publisher")
        client.connect("localhost", 1883, 60)
        
        # Send a test message
        test_message = {
            "device_id": "frontend2_device",
            "timestamp": "2024-12-04T12:00:00.000Z",
            "displacement": 15.5,
            "force": 45.3,
            "message_id": 999,
            "publisher": "test_publisher"
        }
        
        client.publish("device_data/frontend2_device", json.dumps(test_message), qos=1)
        print("✅ MQTT test message sent")
        
        client.disconnect()
        return True
    except Exception as e:
        print(f"❌ MQTT test failed: {e}")
        return False

def main():
    print("=" * 60)
    print("🧪 Frontend-2 Data Flow Test")
    print("=" * 60)
    
    # Test 1: Backend health
    print("\n1. Testing backend health...")
    backend_ok = test_backend_health()
    
    # Test 2: WebSocket connection
    print("\n2. Testing WebSocket connection...")
    websocket_ok = test_websocket_connection()
    
    # Test 3: MQTT publisher
    print("\n3. Testing MQTT publisher...")
    mqtt_ok = test_mqtt_publisher()
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Results:")
    print(f"   Backend Health: {'✅ PASS' if backend_ok else '❌ FAIL'}")
    print(f"   WebSocket: {'✅ PASS' if websocket_ok else '❌ FAIL'}")
    print(f"   MQTT Publisher: {'✅ PASS' if mqtt_ok else '❌ FAIL'}")
    
    if backend_ok and websocket_ok and mqtt_ok:
        print("\n🎉 All tests passed! Frontend-2 should be receiving data.")
        print("\n📋 Next steps:")
        print("1. Open http://localhost:3002 in your browser")
        print("2. Check browser console for WebSocket messages")
        print("3. Verify data is being displayed in the chart")
    else:
        print("\n⚠️  Some tests failed. Check the issues above.")
    
    print("=" * 60)

if __name__ == "__main__":
    main()
