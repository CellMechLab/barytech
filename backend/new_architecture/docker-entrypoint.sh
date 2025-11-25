#!/usr/bin/env sh
set -e

# Create authentication if credentials are provided via environment variables
if [ -n "$MOSQ_USER" ] && [ -n "$MOSQ_PASS" ]; then
  touch /mosquitto/config/passwordfile
  mosquitto_passwd -b /mosquitto/config/passwordfile "$MOSQ_USER" "$MOSQ_PASS"
fi

# Write mosquitto configuration file
# Render terminates TLS; broker speaks plain WebSockets internally
cat >/mosquitto/config/mosquitto.conf <<'EOF'
persistence true
persistence_location /mosquitto/data/
log_timestamp true
allow_anonymous false
password_file /mosquitto/config/passwordfile

# Bind raw MQTT internally (not public on Web Service)
listener 1883 0.0.0.0
EOF

# Add WebSocket listener if PORT environment variable is set
if [ -n "$PORT" ]; then
  {
    echo "listener $PORT 0.0.0.0"
    echo "protocol websockets"
    # Optional: force IPv4 if you hit WebSocket bind quirks
    # echo "socket_domain ipv4"
  } >> /mosquitto/config/mosquitto.conf
fi

# Start mosquitto with the generated configuration
exec mosquitto -c /mosquitto/config/mosquitto.conf







