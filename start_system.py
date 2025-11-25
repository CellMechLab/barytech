#!/usr/bin/env python3
"""
Unified System Startup Script
Starts Kafka, Mosquitto, and Backend in the correct order
"""

import os
import sys
import time
import subprocess
import signal
import threading
from pathlib import Path

class SystemManager:
    def __init__(self):
        self.processes = {}
        self.running = True
        self.project_root = Path(__file__).parent
        
    def log(self, message, level="INFO"):
        """Unified logging"""
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")
        
    def run_command(self, name, command, cwd=None, background=True):
        """Run a command and track the process"""
        try:
            self.log(f"Starting {name}...")
            
            if background:
                process = subprocess.Popen(
                    command,
                    shell=True,
                    cwd=cwd or self.project_root,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    bufsize=1
                )
                self.processes[name] = process
                
                # Start output monitoring thread with filtering
                def monitor_output():
                    # Keywords to filter out (reduce noise but keep important Kafka diagnostic info)
                    filter_keywords = [
                        'DEBUG',                 # keep
                        'Loaded member MemberMetadata',
                        'Finished loading offsets',
                        'Loading group metadata'
                        # REMOVED: 'aiokafka.consumer', 'aiokafka.producer', 'kafka.coordinator', 'kafka.cluster', 'GroupCoordinator', 'GroupMetadataManager'
                    ]
                    
                    for line in process.stdout:
                        if self.running:
                            line_stripped = line.strip()
                            # Skip noisy debug lines
                            if not any(keyword in line_stripped for keyword in filter_keywords):
                                print(f"[{name}] {line_stripped}")
                
                thread = threading.Thread(target=monitor_output, daemon=True)
                thread.start()
                
                return process
            else:
                result = subprocess.run(
                    command,
                    shell=True,
                    cwd=cwd or self.project_root,
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    self.log(f"Command failed: {result.stderr}", "ERROR")
                    return False
                else:
                    self.log(f"Command succeeded: {result.stdout}")
                    return True
                    
        except Exception as e:
            self.log(f"Error running {name}: {e}", "ERROR")
            return None
            
    def wait_for_service(self, name, check_command, timeout=30):
        """Wait for a service to be ready"""
        self.log(f"Waiting for {name} to be ready...")
        
        for i in range(timeout):
            try:
                result = subprocess.run(
                    check_command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    self.log(f"✅ {name} is ready!")
                    return True
            except:
                pass
                
            if i < timeout - 1:  # Don't sleep on last iteration
                time.sleep(1)
                
        self.log(f"❌ {name} failed to start within {timeout}s", "ERROR")
        return False

    def wait_for_kafka(self, timeout=180):
        """Wait for Kafka to be ready with proper image compatibility"""
        self.log("Waiting for Kafka to be ready...")

        # candidates: (topic cmd, bootstrap)
        topic_cmds = [
            # Bitnami paths
            'bash -lc "/opt/bitnami/kafka/bin/kafka-topics.sh --bootstrap-server {bs} --list"',
            # Confluent typical path in PATH
            'bash -lc "kafka-topics --bootstrap-server {bs} --list"',
            'bash -lc "/usr/bin/kafka-topics --bootstrap-server {bs} --list"',
            # Wurstmeister style
            'bash -lc "/opt/kafka/bin/kafka/bin/kafka-topics.sh --bootstrap-server {bs} --list"',
            # Lightweight API probe
            'bash -lc "kafka-broker-api-versions --bootstrap-server {bs} >/dev/null 2>&1"'
        ]
        bootstrap_servers = ["kafka:9092", "localhost:9092"]

        for i in range(timeout):
            for bs in bootstrap_servers:
                for cmd_tpl in topic_cmds:
                    cmd = f'docker-compose -f docker-compose.kafka.yml exec -T kafka {cmd_tpl.format(bs=bs)}'
                    try:
                        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
                        if result.returncode == 0:
                            self.log(f"✅ Kafka is ready (checked via {bs}).")
                            return True
                        else:
                            # Surface first few errors early in the wait
                            if i < 5:
                                self.log(f"Kafka check failed (cmd: {cmd_tpl.split()[1]} bs={bs}): {result.stderr.strip() or result.stdout.strip()}", "DEBUG")
                    except Exception as e:
                        if i < 5:
                            self.log(f"Kafka check exception: {e}", "DEBUG")
            
            # Show progress every 30 seconds
            if i % 30 == 0 and i > 0:
                self.log(f"Still waiting for Kafka... ({i}/{timeout}s elapsed)")
                
            time.sleep(1)

        # If we get here, Kafka failed to start. Show some diagnostic info
        self.log("❌ Kafka failed readiness check. Showing diagnostic info:", "ERROR")
        try:
            # Check container status
            result = subprocess.run(
                "docker-compose -f docker-compose.kafka.yml ps kafka",
                shell=True, capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                self.log(f"Kafka container status: {result.stdout.strip()}")
            
            # Show recent Kafka logs
            result = subprocess.run(
                "docker-compose -f docker-compose.kafka.yml logs --tail=20 kafka",
                shell=True, capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                self.log(f"Recent Kafka logs: {result.stdout.strip()}")
                
        except Exception as e:
            self.log(f"Could not get diagnostic info: {e}")
            
        # Run additional debugging
        self.debug_kafka_container()
            
        return False

    def debug_kafka_container(self):
        """Debug what's available in the Kafka container"""
        self.log("🔍 Debugging Kafka container...")
        
        debug_commands = [
            "which kafka-topics",
            "which kafka-topics.sh", 
            "ls -la /usr/bin/ | grep kafka",
            "ls -la /opt/ | grep kafka",
            "echo $PATH",
            "kafka-topics --version 2>&1 || echo 'kafka-topics not found'",
            "kafka-topics.sh --version 2>&1 || echo 'kafka-topics.sh not found'"
        ]
        
        for cmd in debug_commands:
            try:
                result = subprocess.run(
                    f'docker-compose -f docker-compose.kafka.yml exec -T kafka {cmd}',
                    shell=True, capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    self.log(f"✅ {cmd}: {result.stdout.strip()}")
                else:
                    self.log(f"❌ {cmd}: {result.stderr.strip() or result.stdout.strip()}")
            except Exception as e:
                self.log(f"💥 {cmd} failed: {e}")
        
    def start_timescaledb(self):
        """Start TimescaleDB container"""
        self.log("🗄️ Starting TimescaleDB container...")
        
        # Check if TimescaleDB container already exists and is running
        try:
            result = subprocess.run(
                "docker ps --filter name=timescaledb --format '{{.Status}}'",
                shell=True,
                capture_output=True,
                text=True
            )
            if "Up" in result.stdout:
                self.log("✅ TimescaleDB already running")
                return True
        except:
            pass
        
        # Remove existing container if it exists but is stopped
        try:
            subprocess.run(
                "docker rm -f timescaledb",
                shell=True,
                capture_output=True,
                text=True
            )
        except:
            pass
        
        # Start TimescaleDB container with persistent volume
        timescaledb_cmd = (
            "docker run -d --name timescaledb "
            "-e POSTGRES_PASSWORD=calculator1 "
            "-e POSTGRES_DB=schaefer "
            "-e POSTGRES_USER=postgres "
            "-p 5433:5432 "
            "-v timescaledb_data:/var/lib/postgresql/data "
            "timescale/timescaledb:latest-pg15"
        )
        
        if not self.run_command("timescaledb", timescaledb_cmd, background=False):
            self.log("❌ Failed to start TimescaleDB container", "ERROR")
            return False
        
        # Wait for TimescaleDB to be ready
        return self.wait_for_timescaledb(timeout=60)
    
    def wait_for_timescaledb(self, timeout=60):
        """Wait for TimescaleDB to be ready"""
        self.log("Waiting for TimescaleDB to be ready...")
        
        for i in range(timeout):
            try:
                # Test connection to TimescaleDB
                result = subprocess.run(
                    "docker exec timescaledb pg_isready -h localhost -p 5432",
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    self.log("✅ TimescaleDB is ready!")
                    return True
            except:
                pass
                
            if i < timeout - 1:  # Don't sleep on last iteration
                time.sleep(1)
                
        self.log(f"❌ TimescaleDB failed to start within {timeout}s", "ERROR")
        return False

    def start_kafka_stack(self):
        """Start Kafka and Zookeeper using Docker Compose"""
        self.log("🐳 Starting Kafka stack with Docker Compose...")
        
        # Check if Docker is running
        if not self.run_command("docker-check", "docker info", background=False):
            self.log("❌ Docker is not running. Please start Docker first.", "ERROR")
            return False
            
        # Start Kafka stack with full logging (don't filter out important Kafka diagnostic info)
        kafka_process = self.run_command(
            "kafka-stack", 
            "docker-compose -f docker-compose.kafka.yml up",
            background=True
        )
        
        if not kafka_process:
            return False
            
        # Wait for Kafka to be ready using the proper method
        return self.wait_for_kafka(timeout=180)
        
    def start_mosquitto(self):
        """Start Mosquitto MQTT broker"""
        self.log("🦟 Starting Mosquitto MQTT broker...")
        
        # Check if Mosquitto is already running
        try:
            result = subprocess.run(
                "netstat -an | grep :1883",
                shell=True,
                capture_output=True,
                text=True
            )
            if "LISTENING" in result.stdout:
                self.log("⚠️  Mosquitto already running on port 1883")
                return True
        except:
            pass
            
        # Start Mosquitto with our config (try multiple possible paths)
        mosquitto_paths = [
            '"/c/Program Files/mosquitto/mosquitto"',
            '"C:/Program Files/mosquitto/mosquitto.exe"',
            'mosquitto'  # If in PATH
        ]
        
        mosquitto_process = None
        for path in mosquitto_paths:
            try:
                mosquitto_process = self.run_command(
                    "mosquitto",
                    f'{path} -c mosquitto.conf',
                    background=True
                )
                if mosquitto_process:
                    break
            except:
                continue
        
        if not mosquitto_process:
            self.log("❌ Could not start Mosquitto - please check if it's installed", "ERROR")
            return False
            
        # Wait for Mosquitto to be ready
        return self.wait_for_service(
            "Mosquitto",
            "netstat -an | grep :1883",
            timeout=10
        )
        
    def setup_kafka_topics(self):
        """Create necessary Kafka topics using container CLI"""
        self.log("📋 Setting up Kafka topics...")

        # Create topics using Kafka CLI from inside the container
        # This ensures we use the correct bootstrap server and have all dependencies
        topics = [
            {
                "name": "iot_raw_ingestion",
                "partitions": 96,
                "replication_factor": 1
            },
            {
                "name": "iot_raw_ingestion_dlq", 
                "partitions": 24,
                "replication_factor": 1
            }
        ]
        
        for topic in topics:
            cmd = (
                f'docker-compose -f docker-compose.kafka.yml exec -T kafka '
                f'kafka-topics --bootstrap-server kafka:9092 '
                f'--create --if-not-exists '
                f'--topic {topic["name"]} '
                f'--replication-factor {topic["replication_factor"]} '
                f'--partitions {topic["partitions"]}'
            )
            
            self.log(f"Creating topic: {topic['name']}")
            if not self.run_command(f"create-topic-{topic['name']}", cmd, background=False):
                self.log(f"❌ Failed to create topic {topic['name']}", "ERROR")
                return False
                
        self.log("✅ All Kafka topics created successfully")
        return True
        
    def start_backend(self, kafka_mode=True):
        """Start the backend application (shell-free, portable)."""
        self.log("🚀 Starting backend application...")

        backend_dir = self.project_root / "backend" / "new_architecture"
        if not backend_dir.exists():
            self.log(f"Backend dir not found: {backend_dir}", "ERROR")
            return False

        # Pick venv python
        if os.name == "nt":
            py_exe = backend_dir / "venv" / "Scripts" / "python.exe"
        else:
            py_exe = backend_dir / "venv" / "bin" / "python"

        if not os.path.exists(py_exe):
            self.log(f"Python executable not found: {py_exe}", "ERROR")
            return False

        # Prepare environment (no shell 'set' needed)
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"   # avoid emoji crashes on Windows
        env["PYTHONUTF8"] = "1"
        if kafka_mode:
            env["KAFKA_FIRST_MODE"] = "true"          # enable Kafka-first handler
            env["PIPELINE_MODE"] = "kafka_first"      # tell MQTT mux to use Kafka-first

        try:
            self.log("Starting backend...")
            process = subprocess.Popen(
                [str(py_exe), "run.py"],   # Use fixed run_fixed.py with better error handling
                cwd=str(backend_dir),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            self.processes["backend"] = process

            def monitor_output():
                filter_keywords = [
                    "DEBUG",
                    "Loaded member MemberMetadata",
                    "Finished loading offsets",
                    "Loading group metadata",
                ]
                for line in process.stdout:
                    if self.running:
                        s = line.strip()
                        if not any(k in s for k in filter_keywords):
                            print(f"[backend] {s}")

            threading.Thread(target=monitor_output, daemon=True).start()

        except Exception as e:
            self.log(f"Failed to start backend: {e}", "ERROR")
            return False

        return self.wait_for_backend_health(timeout=45)

    def wait_for_backend_health(self, timeout=45):
        """Portable health probe (no curl)."""
        import http.client, socket, time as _time
        self.log("Waiting for Backend to be ready...")
        deadline = _time.time() + timeout
        while _time.time() < deadline:
            try:
                conn = http.client.HTTPConnection("localhost", 8000, timeout=2)
                conn.request("GET", "/monitoring/health")
                resp = conn.getresponse()
                if 200 <= resp.status < 300:
                    self.log("✅ Backend is ready!")
                    conn.close()
                    return True
                conn.close()
            except (ConnectionRefusedError, socket.timeout, OSError):
                pass
            _time.sleep(1)
        self.log(f"❌ Backend failed to start within {timeout}s", "ERROR")
        return False
        
    def start_full_system(self):
        """Start the complete system"""
        self.log("[STARTUP] Starting IoT High-Performance System")
        self.log("=" * 60)
        
        try:
            # Step 1: Start TimescaleDB
            if not self.start_timescaledb():
                self.log("[ERROR] Failed to start TimescaleDB", "ERROR")
                return False
                
            # Step 2: Start Kafka stack
            if not self.start_kafka_stack():
                self.log("[ERROR] Failed to start Kafka stack", "ERROR")
                return False
                
            # Step 3: Setup Kafka topics
            if not self.setup_kafka_topics():
                self.log("[ERROR] Failed to setup Kafka topics", "ERROR")
                return False
                
            # Step 4: Start Mosquitto
            if not self.start_mosquitto():
                self.log("[ERROR] Failed to start Mosquitto", "ERROR")
                return False
                
            # Step 5: Start backend
            if not self.start_backend(kafka_mode=True):
                self.log("[ERROR] Failed to start backend", "ERROR")
                return False
                
            self.log("[SUCCESS] System startup completed successfully!")
            self.log("=" * 60)
            self.log("[INFO] Services running:")
            self.log("   - TimescaleDB: localhost:5433")
            self.log("   - Kafka: localhost:9092")
            self.log("   - Kafka UI: http://localhost:8080")
            self.log("   - Mosquitto: localhost:1883")
            self.log("   - Backend API: http://localhost:8000")
            self.log("   - Health Check: http://localhost:8000/monitoring/health")
            self.log("   - Metrics: http://localhost:8000/monitoring/stats")
            self.log("=" * 60)
            self.log("[READY] Ready for high-performance IoT data processing with TimescaleDB!")
            
            return True
            
        except KeyboardInterrupt:
            self.log("[INTERRUPT] Startup interrupted by user")
            return False
        except Exception as e:
            self.log(f"[ERROR] Unexpected error during startup: {e}", "ERROR")
            return False
            
    def start_mqtt_only_system(self):
        """Start system without Kafka (MQTT + Backend only)"""
        self.log("[STARTUP] Starting MQTT-Only System (Direct Processing)")
        self.log("=" * 60)
        
        try:
            # Step 1: Start Mosquitto
            if not self.start_mosquitto():
                self.log("[ERROR] Failed to start Mosquitto", "ERROR")
                return False
                
            # Step 2: Start backend without Kafka
            if not self.start_backend(kafka_mode=False):
                self.log("[ERROR] Failed to start backend", "ERROR")
                return False
                
            self.log("[SUCCESS] MQTT-only system startup completed!")
            self.log("=" * 60)
            self.log("[INFO] Services running:")
            self.log("   - Mosquitto: localhost:1883")
            self.log("   - Backend API: http://localhost:8000")
            self.log("   - Health Check: http://localhost:8000/monitoring/health")
            self.log("=" * 60)
            self.log("[READY] Ready for direct MQTT processing!")
            
            return True
            
        except KeyboardInterrupt:
            self.log("[INTERRUPT] Startup interrupted by user")
            return False
        except Exception as e:
            self.log(f"[ERROR] Unexpected error during startup: {e}", "ERROR")
            return False
            
    def stop_system(self):
        """Stop all services"""
        self.log("STOP: Stopping system...")
        self.running = False
        
        # Stop all tracked processes
        for name, process in self.processes.items():
            try:
                self.log(f"Stopping {name}...")
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.log(f"Force killing {name}...")
                process.kill()
            except Exception as e:
                self.log(f"Error stopping {name}: {e}", "ERROR")
                
        # Stop Docker Compose
        try:
            subprocess.run(
                "docker-compose -f docker-compose.kafka.yml down",
                shell=True,
                cwd=self.project_root,
                timeout=30
            )
        except Exception as e:
            self.log(f"Error stopping Docker Compose: {e}", "ERROR")
        
        # Stop TimescaleDB container (preserve volume)
        try:
            subprocess.run(
                "docker stop timescaledb",
                shell=True,
                timeout=10
            )
            self.log("✅ TimescaleDB stopped (data preserved in volume)")
        except Exception as e:
            self.log(f"Error stopping TimescaleDB: {e}", "ERROR")
            
        self.log("✅ System stopped")
        
    def monitor_system(self):
        """Monitor system and keep it running"""
        try:
            self.log("🔍 Monitoring system... Press Ctrl+C to stop")
            while self.running:
                time.sleep(5)
                
                # Check if processes are still running
                for name, process in list(self.processes.items()):
                    if process.poll() is not None:
                        self.log(f"⚠️  {name} process stopped unexpectedly", "WARNING")
                        
        except KeyboardInterrupt:
            self.log("🛑 Shutdown requested by user")
        finally:
            self.stop_system()

def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python start_system.py full      # Start complete system (Kafka + MQTT + Backend)")
        print("  python start_system.py mqtt      # Start MQTT-only system (Direct processing)")
        print("  python start_system.py stop      # Stop all services")
        sys.exit(1)
        
    manager = SystemManager()
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        manager.stop_system()
        sys.exit(0)
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    mode = sys.argv[1].lower()
    
    if mode == "full":
        if manager.start_full_system():
            manager.monitor_system()
        else:
            sys.exit(1)
            
    elif mode == "mqtt":
        if manager.start_mqtt_only_system():
            manager.monitor_system()
        else:
            sys.exit(1)
            
    elif mode == "stop":
        manager.stop_system()
        
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)

if __name__ == "__main__":
    main()
