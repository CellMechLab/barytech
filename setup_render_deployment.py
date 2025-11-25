#!/usr/bin/env python3
"""
Setup Render Deployment
Creates necessary configuration files for Render deployment
"""

import os
from pathlib import Path

def create_env_files():
    """Create environment configuration files for frontends"""
    
    # Frontend-1 environment file
    frontend1_env = Path("frontend-1/.env.production")
    frontend1_env.write_text("""# Production environment variables for Frontend-1
REACT_APP_BACKEND_URL=https://barytech-backend.onrender.com
REACT_APP_WS_URL=wss://barytech-backend.onrender.com/ws
GENERATE_SOURCEMAP=false
""")
    print(f"✅ Created {frontend1_env}")
    
    # Frontend-2 environment file
    frontend2_env = Path("frontend-2/.env.production")
    frontend2_env.write_text("""# Production environment variables for Frontend-2
REACT_APP_BACKEND_URL=https://barytech-backend.onrender.com
REACT_APP_WS_URL=wss://barytech-backend.onrender.com/ws
GENERATE_SOURCEMAP=false
""")
    print(f"✅ Created {frontend2_env}")

def create_gitignore_updates():
    """Create .gitignore updates for deployment"""
    
    gitignore_content = """
# Render deployment
.env.production
.env.local
.env.development.local
.env.test.local
.env.production.local

# Build outputs
build/
dist/

# Dependencies
node_modules/
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
env/
venv/
.venv/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Logs
*.log
logs/

# Runtime data
pids/
*.pid
*.seed
*.pid.lock

# Coverage directory used by tools like istanbul
coverage/

# nyc test coverage
.nyc_output

# Dependency directories
jspm_packages/

# Optional npm cache directory
.npm

# Optional REPL history
.node_repl_history

# Output of 'npm pack'
*.tgz

# Yarn Integrity file
.yarn-integrity

# dotenv environment variables file
.env

# Database
*.db
*.sqlite
*.sqlite3

# HDF5 files
*.h5
*.hdf5
"""
    
    gitignore_path = Path(".gitignore")
    if gitignore_path.exists():
        with open(gitignore_path, 'a') as f:
            f.write(gitignore_content)
        print(f"✅ Updated .gitignore")
    else:
        gitignore_path.write_text(gitignore_content)
        print(f"✅ Created .gitignore")

def create_deployment_checklist():
    """Create deployment checklist"""
    
    checklist = """# Render Deployment Checklist

## Pre-Deployment
- [ ] Push all code to GitHub repository
- [ ] Test locally with production environment variables
- [ ] Verify all dependencies are in requirements.txt and package.json
- [ ] Check that TimescaleDB extension is available on Render PostgreSQL

## Database Setup
- [ ] Create PostgreSQL database on Render
- [ ] Enable TimescaleDB extension: `CREATE EXTENSION IF NOT EXISTS timescaledb;`
- [ ] Note the connection string for backend configuration

## Backend Deployment
- [ ] Create Web Service for backend
- [ ] Set root directory to: `backend/new_architecture`
- [ ] Configure build command: `pip install -r requirements.txt`
- [ ] Configure start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- [ ] Set environment variables (see render.yaml)
- [ ] Set health check path: `/monitoring/health`
- [ ] Deploy and test API endpoints

## Frontend-1 Deployment
- [ ] Create Static Site for frontend-1
- [ ] Set root directory to: `frontend-1`
- [ ] Configure build command: `npm install && npm run build`
- [ ] Set publish directory: `build`
- [ ] Set environment variables for backend URL
- [ ] Deploy and test WebSocket connection

## Frontend-2 Deployment
- [ ] Create Static Site for frontend-2
- [ ] Set root directory to: `frontend-2`
- [ ] Configure build command: `npm install && npm run build`
- [ ] Set publish directory: `build`
- [ ] Set environment variables for backend URL
- [ ] Deploy and test WebSocket connection

## Post-Deployment Testing
- [ ] Test backend health endpoint: `https://your-backend.onrender.com/monitoring/health`
- [ ] Test backend stats endpoint: `https://your-backend.onrender.com/monitoring/stats`
- [ ] Test WebSocket connection from frontends
- [ ] Test database connectivity
- [ ] Test data saving functionality
- [ ] Monitor logs for any errors

## MQTT/Kafka Considerations
- [ ] Decide on MQTT broker solution (cloud service or remove dependency)
- [ ] Decide on Kafka solution (cloud service or remove dependency)
- [ ] Update configuration accordingly
- [ ] Test message flow end-to-end

## Monitoring Setup
- [ ] Configure health checks in Render
- [ ] Set up log monitoring
- [ ] Configure alerts for service failures
- [ ] Monitor database performance

## Security
- [ ] Review and update CORS settings
- [ ] Ensure environment variables are secure
- [ ] Review database access permissions
- [ ] Test authentication if implemented

## Performance
- [ ] Monitor response times
- [ ] Check database query performance
- [ ] Monitor WebSocket connection stability
- [ ] Test under load if needed
"""
    
    checklist_path = Path("DEPLOYMENT_CHECKLIST.md")
    checklist_path.write_text(checklist)
    print(f"✅ Created {checklist_path}")

def main():
    """Main setup function"""
    print("🚀 Setting up Render deployment configuration...")
    print("=" * 50)
    
    create_env_files()
    create_gitignore_updates()
    create_deployment_checklist()
    
    print("\n✅ Render deployment setup complete!")
    print("\n📋 Next steps:")
    print("1. Review the RENDER_DEPLOYMENT_GUIDE.md")
    print("2. Follow the DEPLOYMENT_CHECKLIST.md")
    print("3. Push changes to GitHub")
    print("4. Create services on Render dashboard")
    print("5. Deploy and test!")

if __name__ == "__main__":
    main()














