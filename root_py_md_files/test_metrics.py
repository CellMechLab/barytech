#!/usr/bin/env python3
"""
Test script to verify Prometheus metrics endpoint
"""

import requests
import time

def test_metrics_endpoint():
    """Test the Prometheus metrics endpoint."""
    try:
        response = requests.get("http://localhost:8000/metrics", timeout=5)
        if response.status_code == 200:
            print("✅ Metrics endpoint working!")
            print(f"Content-Type: {response.headers.get('content-type', 'unknown')}")
            print(f"Content Length: {len(response.text)} bytes")
            
            # Show first few lines of metrics
            lines = response.text.split('\n')[:20]
            print("\n📊 Sample metrics:")
            for line in lines:
                if line.strip() and not line.startswith('#'):
                    print(f"   {line}")
            
            return True
        else:
            print(f"❌ Metrics endpoint failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Metrics endpoint error: {e}")
        return False

def test_health_endpoint():
    """Test the health endpoint."""
    try:
        response = requests.get("http://localhost:8000/monitoring/health", timeout=5)
        if response.status_code == 200:
            health = response.json()
            print("\n✅ Health endpoint working!")
            print(f"   Status: {health.get('status', 'unknown')}")
            print(f"   Parsing Success Rate: {health.get('parsing_success_rate', 0)}%")
            print(f"   Processing Success Rate: {health.get('processing_success_rate', 0)}%")
            print(f"   Broadcast Success Rate: {health.get('broadcast_success_rate', 0)}%")
            return True
        else:
            print(f"❌ Health endpoint failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health endpoint error: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing Prometheus metrics endpoints...")
    
    # Test metrics endpoint
    metrics_ok = test_metrics_endpoint()
    
    # Test health endpoint
    health_ok = test_health_endpoint()
    
    if metrics_ok and health_ok:
        print("\n🎉 All endpoints working correctly!")
    else:
        print("\n⚠️  Some endpoints have issues.")
