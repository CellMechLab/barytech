#!/usr/bin/env python3
"""
System Performance Checker for High-Performance MQTT
Checks current system settings and suggests optimizations
"""

import psutil
import platform
import subprocess
import sys
import os
from datetime import datetime

def run_command(command):
    """Run a command and return output"""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        return result.stdout.strip()
    except Exception as e:
        return f"Error: {e}"

def check_tcp_settings():
    """Check current TCP settings"""
    print("🔍 Checking TCP Settings...")
    tcp_output = run_command("netsh interface tcp show global")
    print(tcp_output)
    print()

def check_network_adapters():
    """Check network adapter settings"""
    print("🔍 Checking Network Adapters...")
    adapters_output = run_command("netsh interface show interface")
    print(adapters_output)
    print()

def check_power_plan():
    """Check current power plan"""
    print("🔍 Checking Power Plan...")
    power_output = run_command("powercfg /getactivescheme")
    print(power_output)
    print()

def check_system_info():
    """Check system information"""
    print("🔍 System Information...")
    print(f"OS: {platform.system()} {platform.release()}")
    print(f"Architecture: {platform.machine()}")
    print(f"Processor: {platform.processor()}")
    print(f"Python Version: {sys.version}")
    print()

def check_memory_usage():
    """Check memory usage"""
    print("🔍 Memory Usage...")
    memory = psutil.virtual_memory()
    print(f"Total Memory: {memory.total / (1024**3):.2f} GB")
    print(f"Available Memory: {memory.available / (1024**3):.2f} GB")
    print(f"Memory Usage: {memory.percent}%")
    print(f"Free Memory: {memory.free / (1024**3):.2f} GB")
    print()

def check_cpu_info():
    """Check CPU information"""
    print("🔍 CPU Information...")
    print(f"CPU Cores: {psutil.cpu_count()}")
    print(f"CPU Logical Cores: {psutil.cpu_count(logical=True)}")
    print(f"CPU Usage: {psutil.cpu_percent(interval=1)}%")
    print()

def check_network_connections():
    """Check current network connections"""
    print("🔍 Network Connections...")
    connections = psutil.net_connections()
    tcp_connections = [conn for conn in connections if conn.status == 'ESTABLISHED']
    print(f"Total TCP Connections: {len(tcp_connections)}")
    print(f"Total Network Connections: {len(connections)}")
    print()

def check_mqtt_ports():
    """Check MQTT-related ports"""
    print("🔍 MQTT Port Status...")
    mqtt_ports = [1883, 8883, 8000, 3001, 3002]
    
    for port in mqtt_ports:
        connections = psutil.net_connections()
        port_connections = [conn for conn in connections if conn.laddr.port == port]
        if port_connections:
            print(f"Port {port}: {len(port_connections)} connections")
            for conn in port_connections[:3]:  # Show first 3
                print(f"  - {conn.laddr.ip}:{conn.laddr.port} -> {conn.raddr.ip if conn.raddr else 'N/A'}:{conn.raddr.port if conn.raddr else 'N/A'} ({conn.status})")
        else:
            print(f"Port {port}: No connections")
    print()

def suggest_optimizations():
    """Suggest optimizations based on current system state"""
    print("🚀 Optimization Suggestions...")
    print()
    
    print("1. TCP/IP Optimizations:")
    print("   - Run: netsh int tcp set global autotuninglevel=normal")
    print("   - Run: netsh int tcp set global chimney=enabled")
    print("   - Run: netsh int tcp set global dca=enabled")
    print("   - Run: netsh int tcp set global rss=enabled")
    print()
    
    print("2. Registry Optimizations:")
    print("   - Increase MaxUserPort to 65534")
    print("   - Set TcpTimedWaitDelay to 30")
    print("   - Increase MaxFreeTcbs to 65536")
    print()
    
    print("3. Power Plan:")
    print("   - Set to High Performance: powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c")
    print()
    
    print("4. Network Adapter Settings:")
    print("   - Disable Flow Control")
    print("   - Disable Interrupt Moderation")
    print("   - Set Jumbo Packet to 1514")
    print()
    
    print("5. Application Optimizations:")
    print("   - Use larger batch sizes (1000+ messages)")
    print("   - Increase MQTT client max_inflight_messages")
    print("   - Use QoS 0 for maximum throughput")
    print("   - Consider using multiple MQTT connections")
    print()

def check_mqtt_broker_status():
    """Check if MQTT broker is running"""
    print("🔍 MQTT Broker Status...")
    connections = psutil.net_connections()
    mqtt_connections = [conn for conn in connections if conn.laddr.port == 1883]
    
    if mqtt_connections:
        print("✅ MQTT Broker (port 1883) is running")
        print(f"   Active connections: {len(mqtt_connections)}")
    else:
        print("❌ MQTT Broker (port 1883) is not running")
    print()

def main():
    """Main function"""
    print("=" * 60)
    print("🔧 System Performance Checker for High-Performance MQTT")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Check if running as administrator
    try:
        is_admin = os.getuid() == 0
    except AttributeError:
        import ctypes
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
    
    if not is_admin:
        print("⚠️  Warning: Not running as administrator")
        print("   Some optimizations may require admin privileges")
        print()
    
    check_system_info()
    check_cpu_info()
    check_memory_usage()
    check_network_connections()
    check_mqtt_ports()
    check_mqtt_broker_status()
    check_tcp_settings()
    check_network_adapters()
    check_power_plan()
    suggest_optimizations()
    
    print("=" * 60)
    print("📋 Quick Optimization Commands:")
    print("=" * 60)
    print("1. Run as Administrator: windows_network_optimization.bat")
    print("2. Or run PowerShell as Administrator: .\\windows_network_optimization.ps1")
    print("3. Restart MQTT applications after optimization")
    print("=" * 60)

if __name__ == "__main__":
    main()
