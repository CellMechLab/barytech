// Defines the base URL for all HTTP requests sent to the backend API.
export const BACKEND_BASE_URL =
  process.env.REACT_APP_BACKEND_URL ||
  process.env.REACT_APP_API_URL ||
  "http://localhost:8000";

// Defines the base URL for the video stream server used in dashboard widgets.
export const VIDEO_BASE_URL =
  process.env.REACT_APP_VIDEO_URL ||
  process.env.REACT_APP_CAMERA_URL ||
  "http://172.20.10.6:8002";

// Defines the base URL used for WebSocket communication with the backend.
export const WEBSOCKET_BASE_URL =
  process.env.REACT_APP_WEBSOCKET_URL ||
  BACKEND_BASE_URL.replace(/^http/, "ws");

// Builds full HTTP endpoint URLs using the configured backend base URL.
export const buildBackendUrl = (path) => `${BACKEND_BASE_URL}${path}`;

// Builds full WebSocket endpoint URLs using the configured WebSocket base URL.
export const buildWebSocketUrl = (path) => `${WEBSOCKET_BASE_URL}${path}`;
