#!/usr/bin/env python3
"""
Start React Frontends
Script to start both frontend-1 and frontend-2 React applications
"""

import subprocess
import time
import os
import sys
import requests
from pathlib import Path

def check_port_available(port):
    """Check if a port is available"""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('localhost', port))
    sock.close()
    return result != 0

def wait_for_server(url, timeout=30):
    """Wait for server to be ready"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, timeout=1)
            if response.status_code == 200:
                return True
        except:
            pass
        time.sleep(1)
    return False

def start_react_app(frontend_dir, port):
    """Start a React app on a specific port"""
    print(f"🚀 Starting {frontend_dir} on port {port}...")
    
    # Set the PORT environment variable
    env = os.environ.copy()
    env['PORT'] = str(port)
    
    try:
        # Start the React app
        process = subprocess.Popen(
            ['npm', 'start'],
            cwd=frontend_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait a bit for the app to start
        time.sleep(5)
        
        # Check if the server is running
        if wait_for_server(f"http://localhost:{port}"):
            print(f"✅ {frontend_dir} is running on http://localhost:{port}")
            return process
        else:
            print(f"❌ {frontend_dir} failed to start on port {port}")
            process.terminate()
            return None
            
    except Exception as e:
        print(f"❌ Error starting {frontend_dir}: {e}")
        return None

def main():
    """Main function to start both React frontends"""
    print("=" * 60)
    print("🚀 Starting React Frontends")
    print("=" * 60)
    
    # Check if we're in the right directory
    if not Path("frontend-1").exists() or not Path("frontend-2").exists():
        print("❌ frontend-1 and frontend-2 directories not found")
        print("Please run this script from the project root directory")
        return
    
    # Check if ports are available
    if not check_port_available(3000):
        print("❌ Port 3000 is already in use")
        return
    
    if not check_port_available(3001):
        print("❌ Port 3001 is already in use")
        return
    
    print("✅ Ports 3000 and 3001 are available")
    
    # Start frontend-1 on port 3000
    frontend1_process = start_react_app("frontend-1", 3000)
    
    # Wait a bit before starting the second app
    time.sleep(3)
    
    # Start frontend-2 on port 3001
    frontend2_process = start_react_app("frontend-2", 3001)
    
    if frontend1_process and frontend2_process:
        print("\n🎉 Both React frontends are running!")
        print("📱 Frontend-1: http://localhost:3000")
        print("📱 Frontend-2: http://localhost:3001")
        print("\nPress Ctrl+C to stop both frontends")
        
        try:
            # Keep the script running
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n⏹️  Stopping React frontends...")
            frontend1_process.terminate()
            frontend2_process.terminate()
            print("✅ React frontends stopped")
    else:
        print("❌ Failed to start one or both React frontends")

if __name__ == "__main__":
    main()
