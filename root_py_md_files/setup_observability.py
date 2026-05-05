#!/usr/bin/env python3
"""
Observability Stack Setup Script

This script sets up the complete observability stack:
1. Prometheus (metrics collection)
2. Grafana (visualization)
3. MQTT Exporter (broker metrics)
4. Admin Panel (simple monitoring)

Usage:
    python setup_observability.py [start|stop|status]
"""

import subprocess
import sys
import time
import requests
import os
from pathlib import Path

class ObservabilityStack:
    def __init__(self):
        self.services = {
            'prometheus': {
                'image': 'prom/prometheus:latest',
                'container_name': 'prometheus',
                'port': 9090,
                'config_file': 'prometheus.yml'
            },
            'grafana': {
                'image': 'grafana/grafana:latest',
                'container_name': 'grafana',
                'port': 3000,
                'default_creds': {'user': 'admin', 'password': 'admin'}
            },
            'mqtt_exporter': {
                'image': 'kpetrem/mqtt-exporter:latest',
                'container_name': 'mqtt-exporter',
                'port': 9344,
                'env_vars': {
                    'MQTT_ADDRESS': '127.0.0.1',
                    'MQTT_TOPICS': '$SYS/#',
                    'PROMETHEUS_PORT': '9344'
                }
            }
        }
    
    def check_docker(self):
        """Check if Docker is available."""
        try:
            result = subprocess.run(['docker', '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                print("✅ Docker is available")
                return True
            else:
                print("❌ Docker is not available")
                return False
        except FileNotFoundError:
            print("❌ Docker is not installed or not in PATH")
            return False
    
    def start_prometheus(self):
        """Start Prometheus container."""
        config_file = Path('prometheus.yml')
        if not config_file.exists():
            print("❌ prometheus.yml not found")
            return False
        
        try:
            cmd = [
                'docker', 'run', '-d',
                '--name', 'prometheus',
                '-p', '9090:9090',
                '-v', f'{config_file.absolute()}:/etc/prometheus/prometheus.yml',
                'prom/prometheus:latest'
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print("✅ Prometheus started successfully")
                return True
            else:
                print(f"❌ Failed to start Prometheus: {result.stderr}")
                return False
        except Exception as e:
            print(f"❌ Error starting Prometheus: {e}")
            return False
    
    def start_grafana(self):
        """Start Grafana container."""
        try:
            cmd = [
                'docker', 'run', '-d',
                '--name', 'grafana',
                '-p', '3000:3000',
                'grafana/grafana:latest'
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print("✅ Grafana started successfully")
                return True
            else:
                print(f"❌ Failed to start Grafana: {result.stderr}")
                return False
        except Exception as e:
            print(f"❌ Error starting Grafana: {e}")
            return False
    
    def start_mqtt_exporter(self):
        """Start MQTT Exporter container."""
        try:
            cmd = [
                'docker', 'run', '-d',
                '--name', 'mqtt-exporter',
                '--network', 'host',
                '-e', 'MQTT_ADDRESS=127.0.0.1',
                '-e', 'MQTT_TOPICS=$SYS/#',
                '-e', 'PROMETHEUS_PORT=9344',
                'kpetrem/mqtt-exporter:latest'
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print("✅ MQTT Exporter started successfully")
                return True
            else:
                print(f"❌ Failed to start MQTT Exporter: {result.stderr}")
                return False
        except Exception as e:
            print(f"❌ Error starting MQTT Exporter: {e}")
            return False
    
    def stop_service(self, service_name):
        """Stop a specific service."""
        try:
            cmd = ['docker', 'stop', service_name]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"✅ {service_name} stopped successfully")
                return True
            else:
                print(f"❌ Failed to stop {service_name}: {result.stderr}")
                return False
        except Exception as e:
            print(f"❌ Error stopping {service_name}: {e}")
            return False
    
    def remove_service(self, service_name):
        """Remove a specific service container."""
        try:
            cmd = ['docker', 'rm', service_name]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"✅ {service_name} removed successfully")
                return True
            else:
                print(f"❌ Failed to remove {service_name}: {result.stderr}")
                return False
        except Exception as e:
            print(f"❌ Error removing {service_name}: {e}")
            return False
    
    def check_service_status(self, service_name, port):
        """Check if a service is running and accessible."""
        try:
            response = requests.get(f'http://localhost:{port}', timeout=5)
            if response.status_code == 200:
                print(f"✅ {service_name} is running on port {port}")
                return True
            else:
                print(f"⚠️  {service_name} is running but returned status {response.status_code}")
                return False
        except requests.exceptions.RequestException:
            print(f"❌ {service_name} is not accessible on port {port}")
            return False
    
    def start_all(self):
        """Start all observability services."""
        print("🚀 Starting Observability Stack...")
        
        if not self.check_docker():
            return False
        
        success = True
        
        # Start Prometheus
        if not self.start_prometheus():
            success = False
        
        # Start Grafana
        if not self.start_grafana():
            success = False
        
        # Start MQTT Exporter
        if not self.start_mqtt_exporter():
            success = False
        
        if success:
            print("\n⏳ Waiting for services to start...")
            time.sleep(10)
            
            print("\n📊 Checking service status...")
            self.check_service_status('Prometheus', 9090)
            self.check_service_status('Grafana', 3000)
            self.check_service_status('MQTT Exporter', 9344)
            
            print("\n🎉 Observability Stack Setup Complete!")
            print("\n📋 Access URLs:")
            print("   • Prometheus: http://localhost:9090")
            print("   • Grafana: http://localhost:3000 (admin/admin)")
            print("   • MQTT Exporter: http://localhost:9344")
            print("   • Admin Panel: http://localhost:8000/admin_panel.html")
            print("   • Backend Metrics: http://localhost:8000/metrics")
        
        return success
    
    def stop_all(self):
        """Stop all observability services."""
        print("🛑 Stopping Observability Stack...")
        
        success = True
        for service_name in self.services.keys():
            if not self.stop_service(service_name):
                success = False
        
        if success:
            print("✅ All services stopped successfully")
        
        return success
    
    def remove_all(self):
        """Remove all observability service containers."""
        print("🗑️  Removing Observability Stack containers...")
        
        success = True
        for service_name in self.services.keys():
            if not self.remove_service(service_name):
                success = False
        
        if success:
            print("✅ All containers removed successfully")
        
        return success
    
    def status(self):
        """Check status of all services."""
        print("📊 Observability Stack Status:")
        
        for service_name, config in self.services.items():
            print(f"\n🔍 {service_name.upper()}:")
            self.check_service_status(service_name, config['port'])
    
    def setup_grafana_dashboard(self):
        """Setup Grafana dashboard with MQTT metrics."""
        print("📊 Setting up Grafana dashboard...")
        
        # Wait for Grafana to be ready
        time.sleep(15)
        
        try:
            # Login to Grafana
            login_data = {
                'user': 'admin',
                'password': 'admin'
            }
            
            session = requests.Session()
            response = session.post('http://localhost:3000/api/login', json=login_data)
            
            if response.status_code == 200:
                print("✅ Logged into Grafana")
                
                # Add Prometheus data source
                datasource = {
                    'name': 'Prometheus',
                    'type': 'prometheus',
                    'url': 'http://host.docker.internal:9090',
                    'access': 'proxy'
                }
                
                response = session.post('http://localhost:3000/api/datasources', json=datasource)
                if response.status_code == 200:
                    print("✅ Prometheus data source added")
                else:
                    print(f"⚠️  Failed to add Prometheus data source: {response.status_code}")
                
                print("\n📋 Next steps:")
                print("   1. Open Grafana: http://localhost:3000")
                print("   2. Login with admin/admin")
                print("   3. Create a new dashboard")
                print("   4. Add panels for the following metrics:")
                print("      • rate(mqtt_messages_received_total[1m])")
                print("      • ingress_queue_length")
                print("      • device_queue_length")
                print("      • ws_connections")
                print("      • db_batch_writes_total")
                
            else:
                print(f"❌ Failed to login to Grafana: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Error setting up Grafana dashboard: {e}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python setup_observability.py [start|stop|remove|status|setup-dashboard]")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    stack = ObservabilityStack()
    
    if command == 'start':
        stack.start_all()
    elif command == 'stop':
        stack.stop_all()
    elif command == 'remove':
        stack.remove_all()
    elif command == 'status':
        stack.status()
    elif command == 'setup-dashboard':
        stack.setup_grafana_dashboard()
    else:
        print(f"Unknown command: {command}")
        print("Available commands: start, stop, remove, status, setup-dashboard")

if __name__ == "__main__":
    main()
