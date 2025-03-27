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
  
      const downloadDataBufferAsCSV = () => {
        if (!chartData || chartData.datasets.every((dataset) => dataset.data.length === 0)) {
          alert("No data available to download.");
          return;
        }
  
        const csvContent = [["Index", "Data1_y", "Data2_y"]];
        const maxDataPoints = Math.max(
          chartData.datasets[0].data.length,
          chartData.datasets[1].data.length
        );
  
        for (let i = 0; i < maxDataPoints; i++) {
          const data1_y = chartData.datasets[0].data[i] || "";
          const data2_y = chartData.datasets[1].data[i] || "";
          csvContent.push([i, data1_y, data2_y]);
        }
  
        const csvString = csvContent.map((row) => row.join(",")).join("\n");
        const blob = new Blob([csvString], { type: "text/csv" });
        const url = URL.createObjectURL(blob);
  
        const link = document.createElement("a");
        link.href = url;
        link.download = "chartData_y_values.csv";
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      };
  
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
        downloadDataBufferAsCSV,
      }));
  
      const chartOptions = {
        type: 'line',
        data: {
            labels: Array.from({ length: 10 }, (_, i) => i + 1),
            datasets: [{
                label: 'Random Data',
                data: chartData,
                borderColor: 'steelblue',
                backgroundColor: 'rgba(70,130,180,0.2)',
                borderWidth: 2,
                fill: true,
                tension: 0.1
            }]
        },
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: !isDashboard,
            position: "top",
          },
          tooltip: {
            enabled: true,
          },
        },
        scales: {
          x: {
            title: {
              display: !isDashboard,
              text: "Data Points",
            },
          },
          y: {
            title: {
              display: !isDashboard,
              text: "Value",
            },
            beginAtZero: true,
            suggestedMax: 100
          },
        },
      };
  
      return (
        <div ref={chartRef} style={{ width: "100%", height: "100%" }}>
          <Line data={chartData} options={chartOptions} />
        </div>
      );
    }
  );
  
  export default LineChart;
  