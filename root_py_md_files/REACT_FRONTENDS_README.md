# React Frontends Setup

This document explains how to run the simplified React frontend applications for testing the MQTT data flow.

## 📁 Current Setup

- **Frontend-1**: Simplified React app running on port 3001
- **Frontend-2**: Simplified React app running on port 3002
- **Backend**: FastAPI app running on port 8000
- **MQTT Broker**: Mosquitto running on port 1883

## 🚀 How to Start React Frontends

### Option 1: Using Batch Files (Recommended)

1. **Start Frontend-1** (Port 3001):
   ```bash
   start_frontend1.bat
   ```

2. **Start Frontend-2** (Port 3002):
   ```bash
   start_frontend2.bat
   ```

### Option 2: Manual Start

1. **Start Frontend-1**:
   ```bash
   cd frontend-1
   npm start
   ```

2. **Start Frontend-2** (in a new terminal):
   ```bash
   cd frontend-2
   npm start
   ```

### Option 3: Using Python Script

```bash
python start_react_frontends.py
```

## 🧪 Testing the Setup

Run the test script to verify both frontends are running:

```bash
python test_react_frontends.py
```

## 📱 Access URLs

- **Frontend-1**: http://localhost:3001
- **Frontend-2**: http://localhost:3002
- **Backend API**: http://localhost:8000/docs

## 🔧 Troubleshooting

### Port Already in Use
If you get "port already in use" errors:

1. **Check what's using the port**:
   ```bash
   netstat -an | findstr :3001
   netstat -an | findstr :3002
   ```

2. **Kill existing processes**:
   ```bash
   taskkill /F /IM node.exe
   ```

3. **Restart the frontends**

### Frontend Not Starting
1. **Check dependencies**:
   ```bash
   cd frontend-1
   npm install
   cd ../frontend-2
   npm install
   ```

2. **Check for errors** in the terminal output

3. **Verify Node.js is installed**:
   ```bash
   node --version
   npm --version
   ```

## 📊 Current Status

❌ **Frontend-1**: Needs to be started on http://localhost:3001
❌ **Frontend-2**: Needs to be started on http://localhost:3002

## 🎯 Next Steps

1. **Start both frontends**:
   ```bash
   start_frontend1.bat
   start_frontend2.bat
   ```

2. **Open both frontends** in browser
3. **Run MQTT publishers** to test data flow:
   - `frontend1_publisher.py` for Frontend-1
   - `frontend2_high_performance_publisher.py` for Frontend-2

## 📝 Notes

- These are **simplified React apps** (not exact copies of the original frontend)
- Each app connects to WebSocket on port 8000
- Ports are configured in `package.json` files
- Data will flow: MQTT → Backend → WebSocket → React Frontend
- Frontend-1 uses blue theme, Frontend-2 uses red theme

## 🔄 Data Flow

```
MQTT Publisher → MQTT Broker → Backend → WebSocket → React Frontend
```

1. **MQTT Publisher** sends data to broker
2. **Backend** receives data via MQTT client
3. **Backend** processes and broadcasts via WebSocket
4. **React Frontend** receives data via WebSocket connection
5. **React Frontend** displays data in real-time charts

## 🎨 Features

### Frontend-1 (Port 3001)
- Blue color scheme
- Real-time displacement and force charts
- Message counter and connection status
- Data point history

### Frontend-2 (Port 3002)
- Red color scheme
- Real-time displacement and force charts
- Message counter and connection status
- Data point history

## 📦 Dependencies

Both frontends include:
- React 18 with TypeScript
- Chart.js for data visualization
- WebSocket connection to backend
- Real-time data processing
