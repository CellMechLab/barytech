import React, {
    useContext,
    useEffect,
    useState,
    useRef,
    forwardRef,
    useImperativeHandle,
  } from "react";
  import { Line } from "react-chartjs-2";
  import { useTheme } from "@mui/material";
  import { tokens } from "../../theme";
  import { WebSocketContext } from "./WebSocketProvider";
  import html2canvas from "html2canvas";
  import {
    Chart as ChartJS,
    LineElement,
    CategoryScale,
    LinearScale,
    PointElement,
    Legend,
    Tooltip,
  } from "chart.js";
  
  ChartJS.register(LineElement, CategoryScale, LinearScale, PointElement, Legend, Tooltip);
  
  const LineChart = forwardRef(
    (
      { onDataPointCountChange, isCustomLineColors = false, isDashboard = false },
      ref
    ) => {
      const theme = useTheme();
      const colors = tokens(theme.palette.mode);
      const { dataBuffer, setDataBuffer } = useContext(WebSocketContext);
      const chartRef = useRef(null);
  
      const [chartData, setChartData] = useState({
        labels: [0],
        datasets: [
          {
            label: "Data1",
            data: [0],
            borderColor: isCustomLineColors ? "#4682B4" : "#0000FF",
            backgroundColor: "rgba(70, 130, 180, 0.2)",
          },
          {
            label: "Data2",
            data: [0],
            borderColor: isCustomLineColors ? "#FF6347" : "#FF0000",
            backgroundColor: "rgba(255, 99, 71, 0.2)",
          },
        ],
      });
  
      const [dataPointCount, setDataPointCount] = useState(0);
  
      useEffect(() => {
        if (dataBuffer && dataBuffer.length >= 30) {
          const newCount = dataPointCount + dataBuffer.length;
          setDataPointCount(newCount);
          onDataPointCountChange(newCount);
  
          const data1Sum = dataBuffer.reduce((acc, entry) => acc + (entry.data1 || 0), 0);
          const data2Sum = dataBuffer.reduce((acc, entry) => acc + (entry.data2 || 0), 0);
  
          const data1Avg = data1Sum / dataBuffer.length;
          const data2Avg = data2Sum / dataBuffer.length;
  
          setChartData((prev) => ({
            labels: [...prev.labels, prev.labels.length],
            datasets: [
              {
                ...prev.datasets[0],
                data: [...prev.datasets[0].data, data1Avg],
              },
              {
                ...prev.datasets[1],
                data: [...prev.datasets[1].data, data2Avg],
              },
            ],
          }));
  
          setDataBuffer([]);
        }
      }, [dataBuffer, setDataBuffer, dataPointCount, onDataPointCountChange]);
  
      const downloadChart = () => {
        if (chartRef.current) {
          html2canvas(chartRef.current).then((canvas) => {
            const link = document.createElement("a");
            link.download = "chart.png";
            link.href = canvas.toDataURL();
            link.click();
          });
        }
      };
  
      useImperativeHandle(ref, () => ({
        downloadChart,
      }));
      const chartOptions = {
        type: 'line',
        data: {
          datasets: [{
            label: 'Displacement / Force',
            data: chartData,
            borderColor: 'steelblue',
            backgroundColor: 'rgba(70,130,180,0.2)',
            borderWidth: 2,
            fill: true,
            tension: 0.1,
            parsing: false  // important to use raw x/y
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              display: !isDashboard,
              position: "top",
            },
            tooltip: {
              enabled: true,
              callbacks: {
                label: (ctx) => `Value: ${ctx.parsed.y.toExponential(3)}`
              }
            }
          },
          scales: {
            x: {
              title: {
                display: !isDashboard,
                text: "Data Points",
              },
              type: 'linear'
            },
            y: {
              title: {
                display: !isDashboard,
                text: "Value",
              },
              min: -2e-12,
              max: 2e-12,
              ticks: {
                callback: (value) => value.toExponential(1)
              }
            },
          },
        }
      };
      
  
      return (
        <div ref={chartRef} style={{ width: "100%", height: "100%" }}>
          <Line data={chartData} options={chartOptions} />
        </div>
      );
    }
  );
  
  export default LineChart;
  