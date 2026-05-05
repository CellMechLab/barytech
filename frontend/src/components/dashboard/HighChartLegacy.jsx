import React, {
  useContext,
  useEffect,
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
} from "react";
import Highcharts from "highcharts";
import HighchartsReact from "highcharts-react-official";
import { useTheme, Box, Slider } from "@mui/material";
import { tokens } from "../../theme";
import { WebSocketContext } from "./WebSocketProvider";
import html2canvas from "html2canvas";

const LineChart = forwardRef(
  (
    {
      timeRange,
      onDataPointCountChange,
      isCustomLineColors = false,
      isDashboard = false,
    },
    ref
  ) => {
    const theme = useTheme();
    const colors = tokens(theme.palette.mode);
    const { dataBuffer, setDataBuffer } = useContext(WebSocketContext);
    const chartRef = useRef(null);

    const [chartData, setChartData] = useState([
      {
        name: "Data1",
        color: isCustomLineColors ? "#4682B4" : "#0000FF",
        data: [{ x: new Date().getTime(), y: 0 }], // Timestamp as x
      },
      {
        name: "Data2",
        color: isCustomLineColors ? "#FF6347" : "#FF0000",
        data: [{ x: new Date().getTime(), y: 0 }], // Timestamp as x
      },
    ]);

    // Filter chart data based on time range
    const filteredChartData = chartData.map((series) => ({
      ...series,
      data: series.data.filter((point) => {
        const pointTime = point.x;
        return (
          pointTime >= new Date(timeRange[0]).getTime() &&
          pointTime <= new Date(timeRange[1]).getTime()
        );
      }),
    }));

    const [dataPointCount, setDataPointCount] = useState(0);

    const downloadDataBufferAsCSV = () => {
      if (
        !chartData ||
        chartData.length === 0 ||
        chartData.every((item) => item.data.length === 0)
      ) {
        alert("No data available to download.");
        return;
      }

      const csvContent = [["Index", "Data1_y", "Data2_y"]];

      const maxDataPoints = Math.max(
        chartData[0].data.length,
        chartData[1].data.length
      );

      for (let i = 0; i < maxDataPoints; i++) {
        const data1_y = chartData[0].data[i] ? chartData[0].data[i].y : "";
        const data2_y = chartData[1].data[i] ? chartData[1].data[i].y : "";
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
      if (dataBuffer && dataBuffer.length >= 1) {
        const newCount = dataPointCount + dataBuffer.length;
        setDataPointCount(newCount);
        onDataPointCountChange(newCount);

        const data1Sum = dataBuffer.reduce(
          (acc, entry) => acc + (entry.data1 || 0),
          0
        );
        const data2Sum = dataBuffer.reduce(
          (acc, entry) => acc + (entry.data2 || 0),
          0
        );

        const data1Avg = data1Sum / dataBuffer.length;
        const data2Avg = data2Sum / dataBuffer.length;

        // Use the timestamp from the last entry as the x value
        const lastTimestamp = new Date(
          dataBuffer[dataBuffer.length - 1].timestamp
        ).getTime();

        setChartData((prev) => [
          {
            ...prev[0],
            data: [...(prev[0].data || []), { x: lastTimestamp, y: data1Avg }],
          },
          {
            ...prev[1],
            data: [...(prev[1].data || []), { x: lastTimestamp, y: data2Avg }],
          },
        ]);

        // setDataBuffer([]);
      }
    }, [dataBuffer, dataPointCount, onDataPointCountChange]);

    const downloadChart = () => {
      if (chartRef.current) {
        html2canvas(chartRef.current.container.current).then((canvas) => {
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
      chart: {
        type: "line",
        backgroundColor: colors.primary[400],
        height: 230,
      },
      title: {
        // text: "Line Chart",
        style: {
          color: colors.grey[100],
        },
      },
      xAxis: {
        type: "datetime",
        labels: {
          style: {
            color: colors.grey[100],
          },
        },
      },
      yAxis: {
        title: {
          text: "Value",
          style: {
            color: colors.grey[100],
          },
        },
        labels: {
          style: {
            color: colors.grey[100],
          },
        },
      },
      series: filteredChartData,
      tooltip: {
        shared: true,
        style: {
          color: colors.primary[500],
        },
      },
      legend: {
        itemStyle: {
          color: colors.grey[100],
        },
      },
    };

    return (
      <div ref={chartRef} style={{ width: "100%", height: "100%" }}>
        <HighchartsReact
          highcharts={Highcharts}
          options={chartOptions}
          ref={chartRef}
        />
      </div>
    );
  }
);

export default LineChart;
