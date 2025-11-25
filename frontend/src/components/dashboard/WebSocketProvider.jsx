import React, { createContext, useEffect, useState } from "react";
import { Toaster, toast } from "sonner"; // Import Sonner's Toaster and toast
import { useUser } from "../../context/UserContext"; // Import your UserContext
import pako from "pako"; // Import pako for decompression
import { decompress } from 'fzstd'; // Import zstd for decompression

// Magic headers for compression detection
const MAGIC_ZSTD = new TextEncoder().encode("ZSTD\0");
const MAGIC_ZLIB = new TextEncoder().encode("ZLIB\0");

// Helper function to check if buffer starts with magic header
function startsWithMagic(buf, magic) {
  if (buf.byteLength < magic.length) return false;
  const view = new Uint8Array(buf, 0, magic.length);
  for (let i = 0; i < magic.length; i++) if (view[i] !== magic[i]) return false;
  return true;
}

// ZSTD decoder is now available via fzstd library

// Create a WebSocket context
export const WebSocketContext = createContext(null);

// Provider component
export const WebSocketProvider = ({ children }) => {
  const { user } = useUser(); // Get the login function from UserContext

  const [socket, setSocket] = useState(null);
  const [dataBuffer, setDataBuffer] = useState([]); // State to hold received data
  const [dataBuffer1, setDataBuffer1] = useState([]); // State to hold received data
  const [connected, setConnected] = useState(false);
  
  // ✅ NEW: FRAMES / RECORDS / POINTS counters (aligned with backend)
  const [framesReceived, setFramesReceived] = useState(0);   // # of WS batches (frames)
  const [recordsReceived, setRecordsReceived] = useState(0); // # of objects in all batches
  const [pointsReceived, setPointsReceived] = useState(0);   // # of samples across all batches
  const startTsRef = React.useRef(Date.now());
  
  // ✅ NEW: Helper function to count points in each record
  const countPointsInRecord = (r) => {
    if (!r || typeof r !== 'object') return 0;
    if (Array.isArray(r.points))        return r.points.length;        // prefer explicit field if you have it
    if (Array.isArray(r.force))         return r.force.length;
    if (Array.isArray(r.displacement))  return r.displacement.length;
    if (Array.isArray(r.values))        return r.values.length;
    if (Array.isArray(r.data))          return r.data.length;
    return 1;
  };
  
  // ✅ FIXED: Guard against accidental buffer resets
  useEffect(() => {
    if (!user) {
      console.log("🔄 User logged out, clearing data buffer");
      setDataBuffer([]); // Reset when user is null
      setTotalPoints(0); // Reset point counter
      setBatchCount(0); // Reset batch counter
      // ✅ NEW: Reset frame/record/point counters
      setFramesReceived(0);
      setRecordsReceived(0);
      setPointsReceived(0);
    }
  }, [user]);
  
  // Accumulators for tracking received points (keeping for backward compatibility)
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
      
      // ✅ NEW: Request historical data snapshot on connection
      const connectionMessage = {
        client_id,
        type: "connect",
        request_historical: true,
        device_id: "frontend1_ultra_high_perf_device" // Match the actual device ID from publisher
      };
      
      newSocket.send(JSON.stringify(connectionMessage));
      console.log("📡 Requested historical data snapshot:", connectionMessage);
    };

    newSocket.onmessage = async (event) => {
      try {
        let parsedBatch;
        
        // Handle binary data (Blob) - end-to-end compressed data
        if (event.data instanceof Blob) {
          console.log("Received binary data (Blob), size:", event.data.size);
          
          // Convert Blob to ArrayBuffer
          const blob = event.data;
          const buf = await blob.arrayBuffer();
          const uint8Array = new Uint8Array(buf);
          
          // Debug: Log first few bytes to see what we're dealing with
          console.log("🔍 First 20 bytes:", Array.from(uint8Array.slice(0, 20)).map(b => b.toString(16).padStart(2, '0')).join(' '));
          console.log("🔍 First 20 bytes as text:", new TextDecoder('utf-8', { fatal: false }).decode(uint8Array.slice(0, 20)));
          
          let decompressed;
          
          // Detect compression using magic headers
          if (startsWithMagic(buf, MAGIC_ZSTD)) {
            console.log("🔄 Detected ZSTD compression, decompressing...");
            try {
              const src = new Uint8Array(buf, MAGIC_ZSTD.length);
              const out = decompress(src);
              decompressed = out;
              console.log("✅ Successfully decompressed with ZSTD");
            } catch (zstdError) {
              console.error("❌ ZSTD decompression failed:", zstdError);
              throw zstdError;
            }
          } else if (startsWithMagic(buf, MAGIC_ZLIB)) {
            console.log("🔄 Detected ZLIB compression, decompressing...");
            try {
              const src = new Uint8Array(buf, MAGIC_ZLIB.length);
              decompressed = pako.inflate(src);
              console.log("✅ Successfully decompressed with ZLIB");
            } catch (zlibError) {
              console.error("❌ ZLIB decompression failed:", zlibError);
              throw zlibError;
            }
          } else {
            // No magic header detected - try to decompress anyway (might be compressed without magic header)
            console.log("📄 No magic header detected, trying decompression methods...");
            
            // Try ZLIB first (most common)
            try {
              console.log("🔄 Trying ZLIB decompression without magic header...");
              decompressed = pako.inflate(uint8Array);
              console.log("✅ Successfully decompressed with ZLIB (no magic header)");
            } catch (zlibError) {
              console.log("❌ ZLIB decompression failed, trying ZSTD...");
              
              // Try ZSTD
              try {
                console.log("🔄 Trying ZSTD decompression without magic header...");
                decompressed = decompress(uint8Array);
                console.log("✅ Successfully decompressed with ZSTD (no magic header)");
              } catch (zstdError) {
                console.log("❌ ZSTD decompression failed, treating as plain JSON...");
                // Treat as uncompressed data
                decompressed = uint8Array;
              }
            }
          }
          
          // Parse the decompressed data
          const text = new TextDecoder().decode(decompressed);
          console.log("🔍 Decompressed text preview:", text.slice(0, 100));
          parsedBatch = JSON.parse(text);
          console.log("✅ Successfully parsed decompressed data");
        } 
        // Handle text data (fallback for non-binary messages)
        else if (typeof event.data === 'string') {
          console.log("Received text data, length:", event.data.length);
          try {
            parsedBatch = JSON.parse(event.data);
          } catch {
            console.warn("WS: non-JSON text payload, ignoring", event.data.slice(0, 120));
            return;
          }
        }
        // Handle ArrayBuffer directly
        else if (event.data instanceof ArrayBuffer) {
          console.log("Received ArrayBuffer, size:", event.data.byteLength);
          try {
            const uint8Array = new Uint8Array(event.data);
            const textDecoder = new TextDecoder('utf-8');
            const jsonString = textDecoder.decode(uint8Array);
            parsedBatch = JSON.parse(jsonString);
          } catch (arrayBufferError) {
            console.warn("WS: failed to parse ArrayBuffer data, ignoring", arrayBufferError);
            return;
          }
        }
        else {
          throw new Error(`Unsupported data type: ${typeof event.data}`);
        }

        // --- normalize to array ---
        const toArray = (p) => {
          if (Array.isArray(p)) return p;
          if (p && typeof p === "object") {
            // common wrappers we send from the backend
            if (Array.isArray(p.data)) return p.data;        // { type: "snapshot"|"batch", data: [...] }
            return [p];                                      // single message object
          }
          return [];                                         // unknown / bad payload
        };

        const batch = toArray(parsedBatch);
        if (!batch.length) {
          console.warn("WS: unexpected payload shape", parsedBatch);
          return;
        }

        // ✅ NEW: FRAME ACCOUNTING (aligned with backend metrics)
        // 1 WS message == 1 frame (batch)
        const recordsInBatch = batch.length;
        const pointsInBatch = batch.reduce((acc, r) => acc + countPointsInRecord(r), 0);

        setFramesReceived((f) => f + 1);
        setRecordsReceived((r) => r + recordsInBatch);
        setPointsReceived((p) => p + pointsInBatch);

        // Log payload type for debugging
        if (parsedBatch !== batch) {
          console.log(`WS: normalized payload from ${typeof parsedBatch} to array of ${batch.length} items`);
        }

        // ✅ REMOVED: Duplicate point counting (now handled in frame accounting above)
        // Update legacy counters for backward compatibility
        setBatchCount(pointsInBatch);
        setTotalPoints((prev) => prev + pointsInBatch);
        
        // ✅ OPTIMIZED: Increased buffer size to 500k for ultra-high-throughput data retention
        setDataBuffer((prev) => {
          const next = prev.concat(batch);
          return next.length > 500000 ? next.slice(-500000) : next;
        });
        
        // ✅ ENHANCED: Comprehensive batch logging with correct point counting
        const jsonSize = JSON.stringify(batch).length;
        const rawSizeBytes = (event.data instanceof Blob) ? event.data.size
                            : (event.data instanceof ArrayBuffer) ? event.data.byteLength
                            : (typeof event.data === 'string') ? new TextEncoder().encode(event.data).length : 0;
        
        const compressionPercent = rawSizeBytes && jsonSize
          ? ((1 - rawSizeBytes / jsonSize) * 100).toFixed(1)
          : 'n/a';
        
        console.log(`📊 BATCH ANALYSIS:`);
        console.log(`   📦 Records: ${batch.length}`);
        console.log(`   🔢 Points in batch: ${pointsInBatch}`);
        console.log(`   📈 Total points received (client): ${totalPoints + pointsInBatch}`);
        console.log(`   💾 Buffer size (records): ${dataBuffer.length + batch.length}`);
        console.log(`   🔍 Data Types:`, analyzeBatchTypes(batch));
        console.log(`   📊 Compression: ${rawSizeBytes} bytes → ${jsonSize} chars (${compressionPercent}%)`);
        
        // ✅ ENHANCED: Log individual record details for debugging
        if (batch.length <= 10) {
          console.log(`   📋 Records:`, batch.map((record, i) => 
            `[${i}] ${record.device_id || 'unknown'} - ${record.timestamp || 'no-timestamp'}`
          ));
        } else {
          console.log(`   📋 First 3 records:`, batch.slice(0, 3).map((record, i) => 
            `[${i}] ${record.device_id || 'unknown'} - ${record.timestamp || 'no-timestamp'}`
          ));
          console.log(`   📋 Last 3 records:`, batch.slice(-3).map((record, i) => 
            `[${batch.length - 3 + i}] ${record.device_id || 'unknown'} - ${record.timestamp || 'no-timestamp'}`
          ));
        }
        
        console.log(`Parsed batch of ${batch.length} messages`);
        
      } catch (error) {
        console.error("Error parsing message batch:", error);
        console.error("Raw event data:", event.data);
        console.error("Data type:", typeof event.data);
        console.error("Data constructor:", event.data.constructor.name);
        
        // Don't show toast for every parsing error to avoid spam
        if (error.message.includes("unexpected payload shape")) {
          console.warn("WS: skipping malformed payload");
        } else {
          toast.error("Error parsing WebSocket message!", {
            style: { backgroundColor: "red", color: "white" },
          });
        }
      }
    };

    newSocket.onclose = () => {
      console.log("WebSocket connection closed.");
      toast("WebSocket connection closed.", {
        style: { backgroundColor: "orange", color: "black" },
      });
      const wasConnected = connected; // ✅ FIXED: Capture prior state
      setConnected(false); // Update the connected state to false
      setSocket(null); // Clear the socket on close
      if (wasConnected) { // ✅ FIXED: Use captured state for reconnection
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

  // ✅ NEW: FRONTEND SUMMARY effect (aligned with backend metrics)
  useEffect(() => {
    if (batchCount > 0) {
      const elapsed = Math.max(0.001, (Date.now() - startTsRef.current) / 1000);
      const framesPerSec = (framesReceived / elapsed).toFixed(1);
      const recordsPerSec = (recordsReceived / elapsed).toFixed(1);
      const pointsPerSec = (pointsReceived / elapsed).toFixed(1);
      const avgPtsPerFrm = framesReceived ? (pointsReceived / framesReceived).toFixed(1) : '0.0';

      console.log(`[frontend] 📊 WS STATS:`);
      console.log(`   Frames Consumed: ${framesReceived} (${framesPerSec}/sec)`);
      console.log(`   Records Consumed: ${recordsReceived} (${recordsPerSec}/sec)`);
      console.log(`   Data Points Consumed: ${pointsReceived} (${pointsPerSec}/sec)`);
      console.log(`   Avg Data Points/Frame: ${avgPtsPerFrm}`);
      console.log(`   Buffer: ${dataBuffer.length} records (${((dataBuffer.length/500000)*100).toFixed(1)}% used)`);
    }
  }, [batchCount, framesReceived, recordsReceived, pointsReceived, dataBuffer.length]);

  // ✅ HELPER: Analyze batch data types and structure
  const analyzeBatchTypes = (batch) => {
    if (!Array.isArray(batch) || batch.length === 0) return 'empty';
    
    const types = new Set();
    const deviceIds = new Set();
    const hasTimestamps = new Set();
    
    batch.forEach(record => {
      if (record && typeof record === 'object') {
        types.add(typeof record);
        if (record.device_id) deviceIds.add(record.device_id);
        if (record.timestamp) hasTimestamps.add(true);
      }
    });
    
    return {
      recordType: Array.from(types).join(', '),
      deviceCount: deviceIds.size,
      hasTimestamps: hasTimestamps.has(true),
      sampleKeys: batch[0] ? Object.keys(batch[0]).slice(0, 5) : []
    };
  };

  // ✅ ENHANCED: Get comprehensive WebSocket statistics (aligned with backend)
  const getWebSocketStats = () => ({
    connected,
    // ✅ NEW: Frame/Record/Point counters (aligned with backend)
    framesReceived,
    recordsReceived,
    pointsReceived,
    // ✅ LEGACY: Backward compatibility
    totalPointsReceived: totalPoints,
    totalRecordsReceived: dataBuffer.length,
    // ✅ BUFFER: Current state
    currentBufferSize: dataBuffer.length,
    bufferUtilization: ((dataBuffer.length / 500000) * 100).toFixed(1),
    lastBatchPoints: batchCount,
    // ✅ CALCULATED: Performance metrics
    pointsPerRecord: dataBuffer.length > 0 ? (pointsReceived / dataBuffer.length).toFixed(1) : 0,
    avgPointsPerFrame: framesReceived ? (pointsReceived / framesReceived).toFixed(1) : 0,
    // ✅ TECHNICAL: System info
    compressionEnabled: true, // Since we handle both compressed and uncompressed
    dataTypes: dataBuffer.length > 0 ? analyzeBatchTypes(dataBuffer.slice(-100)) : null
  });

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
        getWebSocketStats, // ✅ NEW: Access to comprehensive stats
        // ✅ NEW: Direct access to aligned counters
        framesReceived,
        recordsReceived,
        pointsReceived,
        // ✅ LEGACY: Backward compatibility
        totalPoints,        // Direct access to total points
        batchCount,         // Direct access to current batch size
      }}
    >
      <Toaster position="bottom-right" /> {/* Add the Toaster component */}
      {children}
    </WebSocketContext.Provider>
  );
};
