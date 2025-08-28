import React, { useState, useEffect, useRef } from 'react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
} from 'chart.js';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

interface DataPoint {
  timestamp: string;
  displacement: number;
  force: number;
  message_id: number;
}

function App() {
  const [isConnected, setIsConnected] = useState(false);
  const [messageCount, setMessageCount] = useState(0);
  const [dataPoints, setDataPoints] = useState<DataPoint[]>([]);
  const [connectionTime, setConnectionTime] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);
  const startTimeRef = useRef<number>(0);

  useEffect(() => {
    // Connect to WebSocket
    const ws = new WebSocket('ws://localhost:8000/ws');
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('Frontend-2: WebSocket connected');
      setIsConnected(true);
      startTimeRef.current = Date.now();
      
      // Send client_id
      ws.send(JSON.stringify({ client_id: "2" }));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('Frontend-2: Received data:', data);
        
        setMessageCount(prev => prev + 1);
        
        // Add new data point
        setDataPoints(prev => {
          const newDataPoint: DataPoint = {
            timestamp: data.timestamp || new Date().toISOString(),
            displacement: data.displacement || 0,
            force: data.force || 0,
            message_id: data.message_id || prev.length + 1
          };
          
          // Keep all data points, no limit
          return [...prev, newDataPoint];
        });
      } catch (error) {
        console.error('Frontend-2: Error parsing message:', error);
      }
    };

    ws.onclose = () => {
      console.log('Frontend-2: WebSocket disconnected');
      setIsConnected(false);
    };

    ws.onerror = (error) => {
      console.error('Frontend-2: WebSocket error:', error);
      setIsConnected(false);
    };

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  // Update connection time
  useEffect(() => {
    if (isConnected) {
      const interval = setInterval(() => {
        setConnectionTime(Math.floor((Date.now() - startTimeRef.current) / 1000));
      }, 1000);
      return () => clearInterval(interval);
    }
  }, [isConnected]);

  // Prepare chart data - show all data points
  const chartData = {
    labels: dataPoints.map((_, index) => `Point ${index + 1}`),
    datasets: [
      {
        label: 'Displacement',
        data: dataPoints.map(point => point.displacement),
        borderColor: 'rgb(255, 159, 64)',
        backgroundColor: 'rgba(255, 159, 64, 0.5)',
        tension: 0.1,
        pointRadius: 3,
        pointHoverRadius: 5,
      },
      {
        label: 'Force',
        data: dataPoints.map(point => point.force),
        borderColor: 'rgb(153, 102, 255)',
        backgroundColor: 'rgba(153, 102, 255, 0.5)',
        tension: 0.1,
        pointRadius: 3,
        pointHoverRadius: 5,
      },
    ],
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'top' as const,
      },
      title: {
        display: true,
        text: `Frontend-2: Real-Time Sensor Data (${dataPoints.length} points)`,
      },
    },
    scales: {
      y: {
        beginAtZero: true,
      },
      x: {
        display: dataPoints.length > 0,
      },
    },
    animation: {
      duration: 0, // Disable animations for better performance
    },
  };

  return (
    <div style={{ padding: '20px', fontFamily: 'Arial, sans-serif' }}>
      <div style={{ 
        backgroundColor: '#fff5f5', 
        padding: '20px', 
        borderRadius: '10px',
        marginBottom: '20px'
      }}>
        <h1 style={{ color: '#dc2626', margin: '0 0 20px 0' }}>
          🔥 Frontend-2 - Real-Time Data Visualization
        </h1>
        
        <div style={{ 
          display: 'flex', 
          gap: '20px', 
          marginBottom: '20px',
          flexWrap: 'wrap'
        }}>
          <div style={{ 
            backgroundColor: 'white', 
            padding: '15px', 
            borderRadius: '8px',
            minWidth: '150px',
            textAlign: 'center',
            boxShadow: '0 2px 5px rgba(220, 38, 38, 0.1)'
          }}>
            <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#dc2626' }}>
              {isConnected ? '🟢' : '🔴'}
            </div>
            <div style={{ fontSize: '14px', color: '#666' }}>
              {isConnected ? 'Connected' : 'Disconnected'}
            </div>
          </div>
          
          <div style={{ 
            backgroundColor: 'white', 
            padding: '15px', 
            borderRadius: '8px',
            minWidth: '150px',
            textAlign: 'center',
            boxShadow: '0 2px 5px rgba(220, 38, 38, 0.1)'
          }}>
            <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#dc2626' }}>
              {messageCount}
            </div>
            <div style={{ fontSize: '14px', color: '#666' }}>
              Messages Received
            </div>
          </div>
          
          <div style={{ 
            backgroundColor: 'white', 
            padding: '15px', 
            borderRadius: '8px',
            minWidth: '150px',
            textAlign: 'center',
            boxShadow: '0 2px 5px rgba(220, 38, 38, 0.1)'
          }}>
            <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#dc2626' }}>
              {dataPoints.length}
            </div>
            <div style={{ fontSize: '14px', color: '#666' }}>
              Data Points
            </div>
          </div>
          
          <div style={{ 
            backgroundColor: 'white', 
            padding: '15px', 
            borderRadius: '8px',
            minWidth: '150px',
            textAlign: 'center',
            boxShadow: '0 2px 5px rgba(220, 38, 38, 0.1)'
          }}>
            <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#dc2626' }}>
              {connectionTime}s
            </div>
            <div style={{ fontSize: '14px', color: '#666' }}>
              Connected Time
            </div>
          </div>
        </div>
      </div>

      <div style={{ 
        backgroundColor: 'white', 
        padding: '20px', 
        borderRadius: '10px',
        boxShadow: '0 2px 10px rgba(220, 38, 38, 0.1)',
        height: '400px'
      }}>
        {dataPoints.length > 0 ? (
          <Line data={chartData} options={chartOptions} />
        ) : (
          <div style={{ 
            textAlign: 'center', 
            padding: '50px', 
            color: '#666',
            fontSize: '18px'
          }}>
            Waiting for data... {isConnected ? 'Connected to backend' : 'Connecting...'}
          </div>
        )}
      </div>

      {dataPoints.length > 0 && (
        <div style={{ 
          backgroundColor: 'white', 
          padding: '20px', 
          borderRadius: '10px',
          marginTop: '20px',
          boxShadow: '0 2px 10px rgba(220, 38, 38, 0.1)'
        }}>
          <h3 style={{ color: '#dc2626' }}>Latest Data Points ({dataPoints.length} total)</h3>
          <div style={{ maxHeight: '200px', overflowY: 'auto' }}>
            {dataPoints.slice(-10).reverse().map((point, index) => (
              <div key={index} style={{ 
                padding: '10px', 
                borderBottom: '1px solid #fee2e2',
                display: 'flex',
                justifyContent: 'space-between'
              }}>
                <span>ID: {point.message_id}</span>
                <span>Displacement: {point.displacement.toFixed(3)}</span>
                <span>Force: {point.force.toFixed(3)}</span>
                <span style={{ fontSize: '12px', color: '#666' }}>
                  {new Date(point.timestamp).toLocaleTimeString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
