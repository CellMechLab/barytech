# Deployment Guide

## Render Deployment

### Prerequisites
- Render account
- PostgreSQL database (can be provisioned through Render)
- MQTT broker (Mosquitto) - needs to be set up separately

### Environment Variables
Set these in your Render service:

- `DATABASE_URL`: PostgreSQL connection string
- `MQTT_BROKER_URL`: MQTT broker hostname
- `MQTT_BROKER_PORT`: MQTT broker port (default: 1883)
- `PYTHON_VERSION`: Python version (3.10.0)

### Deployment Steps

1. **Connect your GitHub repository to Render**
2. **Create a new Web Service**
3. **Configure the service:**
   - Build Command: `cd backend/new_architecture && pip install -r requirements.txt`
   - Start Command: `cd backend/new_architecture && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. **Set environment variables**
5. **Deploy**

### Database Setup

1. Create a PostgreSQL database
2. Run migrations:
   ```bash
   cd backend/new_architecture
   alembic upgrade head
   ```

### MQTT Broker Setup

The application requires an MQTT broker. You can:
1. Use a cloud MQTT service (HiveMQ, AWS IoT, etc.)
2. Set up your own MQTT broker
3. Update the MQTT connection settings in the code

### Frontend Deployment

The frontend can be deployed separately as a static site on:
- Render Static Site
- Netlify
- Vercel
- GitHub Pages

Update the WebSocket URL in `frontend/js/script.js` to point to your backend URL.

## Local Development

### Backend
```bash
cd backend/new_architecture
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend
Open `frontend/index.html` in a browser or serve it with a local server.

### MQTT Broker
```bash
mosquitto -c mosquitto.conf -v
```

### Publisher
```bash
cd backend
python publisher.py 1000 10000
```
