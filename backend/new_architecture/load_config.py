#!/usr/bin/env python3
"""
Configuration Loader
Load environment variables from pipeline_config.env
"""

import os
from pathlib import Path

def load_pipeline_config():
    """Load configuration from pipeline_config.env file"""
    config_file = Path(__file__).parent / "pipeline_config.env"
    
    if not config_file.exists():
        print(f"⚠️ Configuration file not found: {config_file}")
        return
    
    print(f"📋 Loading configuration from: {config_file}")
    
    with open(config_file, 'r') as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if line.startswith('#') or not line:
                continue
            
            # Parse KEY=VALUE format
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # Set environment variable if not already set
                if key not in os.environ:
                    os.environ[key] = value
                    print(f"   ✅ {key}={value}")
                else:
                    print(f"   ⏭️ {key} already set to {os.environ[key]}")

if __name__ == "__main__":
    load_pipeline_config()
    print(f"\n📊 Current environment variables:")
    for key in ["PIPELINE_MODE", "KAFKA_FIRST_MODE", "ENABLE_BROADCAST", "SAVE_FLAG", "VERBOSE_LOGGING"]:
        value = os.getenv(key, "not set")
        print(f"   {key}={value}")














