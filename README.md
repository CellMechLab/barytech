# **Schaefer nanoindenter project**

## **Project Overview**

This project is an IoT system that communicates with devices using **MQTT** and a **FastAPI-based backend**. The frontend is built using **JavaScript** and runs on a basic HTTP server. The project allows **WebSocket communication** with clients and uses MQTT to **publish and subscribe** to messages from a broker.

---

## **Frontend**

The frontend is a **JavaScript-based application** that runs on port `8080` using a basic HTTP server.

### **Running the Frontend**

To run the frontend on port `8080`, follow these steps:

1. Open a terminal and navigate to the directory containing your frontend files (e.g., `index.html`).
2. Run the following command to start the server:

    ```bash
    python -m http.server 8080
    ```

3. This will serve your frontend at **[http://localhost:8080](http://localhost:8080)**.

---

## **Backend**

The backend is built using **FastAPI** and **Paho-MQTT** to handle **WebSocket connections** and communicate with an MQTT broker. The backend is responsible for **broadcasting messages** received from MQTT and processing WebSocket connections.

### **Running the Backend**

The backend runs on port `8000` and communicates with an MQTT broker running on `localhost` at port `1883`.

To set up and run the backend:

1. Install the required libraries using `pip`:

    ```bash
    pip install fastapi paho-mqtt uvicorn asyncio websockets python-multipart
    ```

2. Run the backend using **Uvicorn**:

    ```bash
    python backend.py
    ```

3. The backend will be available at **[http://127.0.0.1:8000](http://127.0.0.1:8000)**.

---

## **Backend Features**

- **WebSocket**: The backend supports WebSocket connections at the `/ws` endpoint. Connected clients will receive messages published to the MQTT broker.
- **MQTT Communication**: The backend uses **Paho-MQTT** to subscribe to the topic `wokwi/MON` and publish messages to the `wokwi/PAR` topic.
- **Message Broadcasting**: Incoming messages from the MQTT broker are broadcast to all connected WebSocket clients in batches.
- **CORS Support**: The backend allows cross-origin requests from **http://localhost** and **http://localhost:8080**.

---

## **Directory Structure**

```bash
.
├── frontend/                  # Frontend files (index.html, main.js, etc.)
├── backend/                    # Backend Python script (FastAPI and MQTT logic)
└── README.md                  # Project documentation
```

## **MQTT Broker Setup**

Ensure that an MQTT broker (such as **Mosquitto**) is running on `localhost` with port `1883`. If you don't have one installed, you can install **Mosquitto** using the following commands:

### **For Ubuntu**:

```bash
sudo apt-get update
sudo apt-get install mosquitto mosquitto-clients
```
### For Mac (using Homebrew):

```bash
brew install mosquitto
```
After installation, start the broker:

```bash
mosquitto
```


