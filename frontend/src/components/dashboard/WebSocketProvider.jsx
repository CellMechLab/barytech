// Provides shared live data-stream and printer-status WebSocket state to the dashboard layout.
import React, { createContext, useEffect, useRef, useState } from "react";
import { Toaster, toast } from "sonner"; // Import Sonner's Toaster and toast
import { useUser } from "../../context/UserContext"; // Import your UserContext
import pako from "pako"; // Import pako for decompression
import { buildWebSocketUrl } from "../../config/endpoints";


// Create a WebSocket context
export const WebSocketContext = createContext(null);

const MAX_DATA_BUFFER_POINTS = Number(
  process.env.REACT_APP_MAX_DATA_BUFFER_POINTS || 5000
);
const DATA_BUFFER_FLUSH_INTERVAL_MS = Number(
  process.env.REACT_APP_DATA_BUFFER_FLUSH_INTERVAL_MS || 100
);

// Provider component
export const WebSocketProvider = ({ children }) => {
  const { user } = useUser(); // Get the login function from UserContext

  const [socket, setSocket] = useState(null);
  const [dataBuffer, setDataBuffer] = useState([]); // State to hold received data
  const [dataBuffer1, setDataBuffer1] = useState([]); // State to hold received data
  const pendingDataMessages = useRef([]);
  const dataBufferFlushTimeout = useRef(null);
  const [connected, setConnected] = useState(false);
  // Tracks whether the shared printer-status WebSocket is currently open.
  const [printerSocketConnected, setPrinterSocketConnected] = useState(false);
  // Stores the latest XYZ position received from the printer-status stream.
  const [printerPosition, setPrinterPosition] = useState({ x: null, y: null, z: null });
  // Stores the latest bed temperature reported by the printer-status stream.
  const [bedTemperature, setBedTemperature] = useState(null);
  // Stores the latest hotend temperature reported by the printer-status stream.
  const [hotendTemperature, setHotendTemperature] = useState(null);
  const [indentationStatus, setIndentationStatus] = useState("Waiting for indentation");
  const previousIndentationState = useRef(null);
  const markIndentationRequested = () => {
    setIndentationStatus("Starting indentation... Waiting for device response.");
  };
  const markIndentationRequestFailed = () => {
    setIndentationStatus("Unable to start indentation. Check the printer connection and try again.");
  };
  const queueDataBufferUpdate = (messages) => {
    pendingDataMessages.current.push(...messages);

    if (dataBufferFlushTimeout.current !== null) {
      return;
    }

    dataBufferFlushTimeout.current = window.setTimeout(() => {
      const queuedMessages = pendingDataMessages.current;
      pendingDataMessages.current = [];
      dataBufferFlushTimeout.current = null;

      setDataBuffer((prev) =>
        [...prev, ...queuedMessages].slice(-MAX_DATA_BUFFER_POINTS)
      );
    }, DATA_BUFFER_FLUSH_INTERVAL_MS);
  };
  useEffect(() => {
    if (!user) {
      setDataBuffer([]); // Reset when user is null
      pendingDataMessages.current = [];

      if (dataBufferFlushTimeout.current !== null) {
        window.clearTimeout(dataBufferFlushTimeout.current);
        dataBufferFlushTimeout.current = null;
      }

      setIndentationStatus("Waiting for indentation");
      previousIndentationState.current = null;
    }
  }, [user]);
  // Tracks received points without triggering an extra React render per batch.
  const totalPoints = useRef(0);

  useEffect(() => {
    if (!user) {
      setPrinterSocketConnected(false);
      setPrinterPosition({ x: null, y: null, z: null });
      setBedTemperature(null);
      setHotendTemperature(null);
      return undefined;
    }

    // Printer-status stream uses the same backend host as HTTP (REACT_APP_BACKEND_URL / API_URL).
    const printerStatusSocketUrl = buildWebSocketUrl("/ws/printer");

    // Keeps track of whether cleanup requested that reconnect attempts stop.
    let shouldReconnect = true;
    // Stores the reconnect timer so cleanup can cancel pending retries.
    let reconnectTimeoutId = null;
    // Stores the current printer WebSocket so cleanup always closes the latest socket.
    let printerSocket = null;

    // Opens the shared printer-status socket and refreshes connection state on each lifecycle event.
    const connectPrinterStatusWebSocket = () => {
      if (!shouldReconnect) {
        return;
      }

      printerSocket = new WebSocket(printerStatusSocketUrl);

      printerSocket.onopen = () => {
        setPrinterSocketConnected(true);
      };

      printerSocket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);

          // Ignores unrelated message types so only printer status updates affect UI state.
          if (message.type !== "printer_status") {
            return;
          }

          // Reads the latest position and temperature values from the printer payload.
          const { position = {}, temperatures = {} } = message;

          setPrinterPosition({
            x: position.X ?? position.x ?? null,
            y: position.Y ?? position.y ?? null,
            z: position.Z ?? position.z ?? null,
          });
          setBedTemperature(temperatures.bed_temp ?? null);
          setHotendTemperature(temperatures.hotend_temp ?? null);
        } catch (error) {
          // Prevents malformed payloads from crashing the shared status stream handler.
          console.error("[printer WS] parse error:", error);
        }
      };

      printerSocket.onclose = () => {
        setPrinterSocketConnected(false);

        // Retries after transient disconnects so the header indicator can recover automatically.
        if (shouldReconnect) {
          reconnectTimeoutId = window.setTimeout(
            connectPrinterStatusWebSocket,
            3000
          );
        }
      };

      printerSocket.onerror = (error) => {
        // Surfaces browser-level socket errors while letting onclose drive reconnect behavior.
        console.error("[printer WS] error:", error);
      };
    };

    connectPrinterStatusWebSocket();

    return () => {
      shouldReconnect = false;

      if (reconnectTimeoutId !== null) {
        window.clearTimeout(reconnectTimeoutId);
      }

      setPrinterSocketConnected(false);
      printerSocket?.close();
    };
  }, [user]);

  const connectWebSocket = () => {
    setIndentationStatus("Waiting for indentation");
    previousIndentationState.current = null;

    const newSocket = new WebSocket(buildWebSocketUrl("/ws"));
    const client_id = user.user_id; // Define the client ID

    newSocket.onopen = () => {
      console.log("WebSocket connection established");
      toast.success("WebSocket connection established!", {
        style: { backgroundColor: "green", color: "white" },
      });
      setConnected(true); // Update the connected state to true
      newSocket.send(JSON.stringify({ client_id })); // Send the client ID
    };

    newSocket.onmessage = async (event) => {
      try {
        let parsedBatch;
        
        // Handle binary data (Blob)
        if (event.data instanceof Blob) {
          // Convert Blob to ArrayBuffer
          const arrayBuffer = await event.data.arrayBuffer();
          const uint8Array = new Uint8Array(arrayBuffer);
          
          // Try to parse as uncompressed binary JSON first
          try {
            const textDecoder = new TextDecoder('utf-8');
            const jsonString = textDecoder.decode(uint8Array);
            parsedBatch = JSON.parse(jsonString);
          } catch (uncompressedError) {
            // If that fails, try to decompress with pako
            try {
              const decompressed = pako.inflate(uint8Array, { to: 'string' });
              parsedBatch = JSON.parse(decompressed);
            } catch (decompressError) {
              console.error("Error decompressing binary data:", decompressError);
              throw new Error(`Failed to parse both uncompressed and compressed data: ${uncompressedError.message} | ${decompressError.message}`);
            }
          }
        } 
        // Handle text data (fallback for non-binary messages)
        else if (typeof event.data === 'string') {
          parsedBatch = JSON.parse(event.data);
        }
        // Handle ArrayBuffer directly
        else if (event.data instanceof ArrayBuffer) {
          const uint8Array = new Uint8Array(event.data);
          const textDecoder = new TextDecoder('utf-8');
          const jsonString = textDecoder.decode(uint8Array);
          parsedBatch = JSON.parse(jsonString);
        }
        else {
          throw new Error(`Unsupported data type: ${typeof event.data}`);
        }

        const parsedMessages = Array.isArray(parsedBatch) ? parsedBatch : [parsedBatch];

        let nextIndentationStatus = null;
        parsedMessages.forEach((message) => {
          if (!message || message.state == null || message.state === "") {
            return;
          }

          const currentState = Number(message.state);

          if (currentState !== 0 && currentState !== 1) {
            return;
          }

          if (currentState === 1) {
            nextIndentationStatus = "Indentation in progress...";
          } else if (previousIndentationState.current === 1) {
            nextIndentationStatus = "Indentation completed. Ready for the next test.";
          }

          previousIndentationState.current = currentState;
        });

        if (nextIndentationStatus) {
          setIndentationStatus(nextIndentationStatus);
        }

        // Store every incoming sample as received, with no idle-based decimation —
        // all values are forwarded to the buffer (still batched into a single React
        // update per flush interval, and capped by MAX_DATA_BUFFER_POINTS).
        totalPoints.current += parsedMessages.length;
        queueDataBufferUpdate(parsedMessages);
        
      } catch (error) {
        console.error("Error parsing message batch:", error);
        console.error("Raw event data:", event.data);
        console.error("Data type:", typeof event.data);
        console.error("Data constructor:", event.data.constructor.name);
        
        toast.error("Error parsing WebSocket message!", {
          style: { backgroundColor: "red", color: "white" },
        });
      }
    };

    newSocket.onclose = () => {
      console.log("WebSocket connection closed.");
      toast("WebSocket connection closed.", {
        style: { backgroundColor: "orange", color: "black" },
      });
      setConnected(false); // Update the connected state to false
      setSocket(null); // Clear the socket on close
      if (connected) {
        console.log("Reconnecting in 2 seconds...");
        setTimeout(connectWebSocket, 2000); // Retry connection after 2 seconds
      }
    };

    newSocket.onerror = (error) => {
      console.error("WebSocket error:", error);
      toast.error("WebSocket encountered an error.", {
        style: { backgroundColor: "red", color: "white" },
      });
      setConnected(false); // Update the connected state to false
    };

    setSocket(newSocket); // Store the new socket in state
  };

  const toggleConnection = () => {
    setConnected((prevConnected) => {
      if (prevConnected && socket) {
        socket.close(); // Close socket if it's currently open
      } else {
        connectWebSocket(); // Connect WebSocket if not connected
      }
      return !prevConnected; // Toggle connected state
    });
  };

  useEffect(() => {
    return () => {
      if (dataBufferFlushTimeout.current !== null) {
        window.clearTimeout(dataBufferFlushTimeout.current);
      }

      if (socket) {
        socket.close(); // Close the socket on cleanup
      }
    };
  }, [socket]); // Run effect only on mount and unmount

  return (
    <WebSocketContext.Provider
      value={{
        socket,
        dataBuffer,
        setDataBuffer,
        toggleConnection,
        connected,
        dataBuffer1,
        setDataBuffer1,
        printerSocketConnected,
        printerPosition,
        bedTemperature,
        hotendTemperature,
        indentationStatus,
        markIndentationRequested,
        markIndentationRequestFailed,
      }}
    >
      <Toaster position="bottom-right" /> {/* Add the Toaster component */}
      {children}
    </WebSocketContext.Provider>
  );
};
