#!/usr/bin/env python3
"""
Fixed version of run.py with better error handling
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Create the app first
app = FastAPI(title="IoT Backend")

# Define allowed origins
origins = [
    "http://localhost",
    "http://localhost:8080",
    "http://localhost:5173",
    "http://127.0.0.1:5173"
]

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- monitoring aliases so external probes work ---
from fastapi import APIRouter

monitor = APIRouter(prefix="/monitoring")

@monitor.get("/health")
async def monitoring_health():
    # Optional: also check sub-app health here
    return {"status": "healthy", "service": "IoT Backend"}

@monitor.get("/stats")
async def monitoring_stats():
    # Return something cheap; fill later with real metrics
    return {"uptime": "ok", "version": "dev"}

app.include_router(monitor)

# Add a simple health check endpoint
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "IoT Backend"}

@app.get("/")
async def root():
    return {"message": "IoT Backend is running!"}

if __name__ == "__main__":
    print("🚀 Starting IoT Backend...")
    print("📡 Will listen on http://0.0.0.0:8000")
    
    try:
        # Try to import and include the main app
        print("📦 Loading main application modules...")
        
        # Import main app safely
        try:
            from app.main import app as main_app
            print("✅ Main app imported successfully")
            
            # Include the main app's routes
            app.mount("/api", main_app)
            print("✅ Main app routes mounted")
            
        except ImportError as e:
            print(f"⚠️  Warning: Could not import main app: {e}")
            print("   Starting with basic endpoints only")
        except Exception as e:
            print(f"⚠️  Warning: Error loading main app: {e}")
            print("   Starting with basic endpoints only")
        
        # Start the server
        print("🚀 Starting server...")
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
        
    except Exception as e:
        print(f"❌ Error starting backend: {e}")
        import traceback
        traceback.print_exc()

