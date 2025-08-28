#!/usr/bin/env python3
"""
Test script for Frontend-1 Publisher
This script runs the frontend1_publisher and provides easy testing
"""

import subprocess
import sys
import time
import os

def check_dependencies():
    """Check if required dependencies are available"""
    try:
        import paho.mqtt.client as mqtt
        print("✅ paho-mqtt is available")
    except ImportError:
        print("❌ paho-mqtt not found. Please install it:")
        print("   pip install paho-mqtt")
        return False
    
    return True

def check_mqtt_broker():
    """Check if MQTT broker is running"""
    try:
        import paho.mqtt.client as mqtt
        client = mqtt.Client()
        client.connect("localhost", 1883, 5)
        client.disconnect()
        print("✅ MQTT broker is running")
        return True
    except Exception as e:
        print(f"❌ MQTT broker is not running: {e}")
        print("   Please start mosquitto broker first")
        return False

def main():
    """Main test function"""
    print("=" * 60)
    print("🧪 Frontend-1 Publisher Test")
    print("=" * 60)
    
    # Check dependencies
    if not check_dependencies():
        return
    
    # Check MQTT broker
    if not check_mqtt_broker():
        return
    
    print("\n📋 Test Instructions:")
    print("1. Open frontend-1.html in your browser")
    print("2. Click 'Start Data Stream' in the frontend")
    print("3. Run this test to send data")
    print("4. Watch the real-time chart update!")
    print("\n" + "=" * 60)
    
    # Ask user if ready
    input("Press Enter when frontend-1.html is ready...")
    
    # Run the publisher
    try:
        print("\n🚀 Starting Frontend-1 Publisher...")
        print("Press Ctrl+C to stop\n")
        
        # Import and run the publisher
        from frontend1_publisher import main as run_publisher
        run_publisher()
        
    except KeyboardInterrupt:
        print("\n⏹️  Test stopped by user")
    except Exception as e:
        print(f"\n❌ Error running publisher: {e}")

if __name__ == "__main__":
    main()
