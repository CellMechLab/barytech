import React, { createContext, useEffect, useState } from "react";
import { Toaster, toast } from "sonner"; // Import Sonner's Toaster and toast
import { useUser } from "../../context/UserContext"; // Import your UserContext


// Create a WebSocket context
export const WebSocketContext = createContext(null);

// Provider component
export const WebSocketProvider = ({ children }) => {
  const { user } = useUser(); // Get the login function from UserContext

  const [socket, setSocket] = useState(null);
  const [dataBuffer, setDataBuffer] = useState([]); // State to hold received data
  const [dataBuffer1, setDataBuffer1] = useState([]); // State to hold received data
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    if (!user) {
      setDataBuffer([]); // Reset when user is null
    }
  }, [user]);
  // Accumulators for tracking received points
  const [batchCount, setBatchCount] = useState(0); // Points in the current batch
  const [totalPoints, setTotalPoints] = useState(0); // Total points received

  const connectWebSocket = () => {
    const newSocket = new WebSocket("ws://127.0.0.1:8000/ws");
    const client_id = user.user_id; // Define the client ID

    newSocket.onopen = () => {
      console.log("WebSocket connection established");
      toast.success("WebSocket connection established!", {
        style: { backgroundColor: "green", color: "white" },
      });
      setConnected(true); // Update the connected state to true
      newSocket.send(JSON.stringify({ client_id })); // Send the client ID
    };

    newSocket.onmessage = (event) => {
      const messageBatch = event.data;
      try {
        const parsedBatch = JSON.parse(messageBatch); // The backend sends a JSON array of objects
        setBatchCount(parsedBatch.length);
        setTotalPoints((prevTotal) => prevTotal + parsedBatch.length);
        setDataBuffer((prev) => [...prev, ...parsedBatch]);
      } catch (error) {
        console.error("Error parsing message batch:", error);
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
      if (socket) {
        socket.close(); // Close the socket on cleanup
      }
    };
  }, [socket]); // Run effect only on mount and unmount

  useEffect(() => {
    if (batchCount > 0) {
      console.log(`Points received in the last batch: ${batchCount}`);
      console.log(`Total points received so far: ${totalPoints}`);
    }
  }, [batchCount, totalPoints]); // Log whenever batchCount or totalPoints changes

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
      }}
    >
      <Toaster position="bottom-right" /> {/* Add the Toaster component */}
      {children}
    </WebSocketContext.Provider>
  );
};
