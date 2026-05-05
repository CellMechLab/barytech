#!/usr/bin/env python3
"""
Test React Frontends
Test script to verify React frontends are running
"""

import requests
import time
import subprocess
import sys

def test_frontend(url, name):
    """Test if a frontend is accessible"""
    try:
        print(f"🔍 Testing {name} at {url}...")
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            print(f"✅ {name} is running at {url}")
            return True
        else:
            print(f"❌ {name} returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ {name} is not accessible: {e}")
        return False

def main():
    """Main test function"""
    print("=" * 60)
    print("🧪 Testing React Frontends")
    print("=" * 60)
    
    # Test frontend-1 on port 3001
    frontend1_ok = test_frontend("http://localhost:3001", "Frontend-1")
    
    # Test frontend-2 on port 3002
    frontend2_ok = test_frontend("http://localhost:3002", "Frontend-2")
    
    print("\n📊 Test Results:")
    if frontend1_ok:
        print("✅ Frontend-1: http://localhost:3001")
    else:
        print("❌ Frontend-1: Not accessible")
        
    if frontend2_ok:
        print("✅ Frontend-2: http://localhost:3002")
    else:
        print("❌ Frontend-2: Not accessible")
    
    if frontend1_ok and frontend2_ok:
        print("\n🎉 Both React frontends are running!")
        print("\n📋 Next Steps:")
        print("1. Open http://localhost:3001 in browser for Frontend-1")
        print("2. Open http://localhost:3002 in browser for Frontend-2")
        print("3. Run your MQTT publishers to test data flow")
    else:
        print("\n❌ Some frontends are not running")
        print("Try starting them with:")
        print("  cd frontend-1 && npm start")
        print("  cd frontend-2 && npm start")

if __name__ == "__main__":
    main()
