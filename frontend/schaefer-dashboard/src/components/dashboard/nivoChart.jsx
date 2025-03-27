import React, {
    useContext,
    useEffect,
    useState,
    useRef,
    forwardRef,
    useImperativeHandle,
  } from "react";
  import { ResponsiveLine } from "@nivo/line";
  import { useTheme } from "@mui/material";
  import { tokens } from "../../theme";
  import { WebSocketContext } from "./WebSocketProvider";
  import html2canvas from "html2canvas";
  
  const LineChart = forwardRef(
    (
      { onDataPointCountChange, isCustomLineColors = false, isDashboard = false },
      ref
    ) => {
      const theme = useTheme();
      const colors = tokens(theme.palette.mode);
      const { dataBuffer, setDataBuffer } = useContext(WebSocketContext);
      const chartRef = useRef(null); // Create a reference for the chart container
  
      const [chartData, setChartData] = useState([
        {
          id: "Data1",
          color: isCustomLineColors ? "#4682B4" : "#0000FF",
          data: [{ x: 0, y: 0 }], // Ensure there is always at least one data point
        },
        {
          id: "Data2",
          color: isCustomLineColors ? "#FF6347" : "#FF0000",
          data: [{ x: 0, y: 0 }], // Ensure there is always at least one data point
        },
      ]);
  
      const [dataPointCount, setDataPointCount] = useState(0);
      // Function to download dataBuffer as CSV
      const downloadDataBufferAsCSV = () => {
        // Check if chartData has data to download
        if (!chartData || chartData.length === 0 || chartData.every(item => item.data.length === 0)) {
          alert("No data available to download.");
          return;
        }
      
        // Define CSV headers
        const csvContent = [
          ["Index", "Data1_y", "Data2_y"], // Only y-axis data with index
        ];
      
        // Determine the maximum number of data points
        const maxDataPoints = Math.max(chartData[0].data.length, chartData[1].data.length);
      
        // Loop through each index to add only y values and index to the CSV
        for (let i = 0; i < maxDataPoints; i++) {
          const data1_y = chartData[0].data[i] ? chartData[0].data[i].y : "";
          const data2_y = chartData[1].data[i] ? chartData[1].data[i].y : "";
          csvContent.push([i, data1_y, data2_y]);
        }
      
        // Convert the CSV array to a string
        const csvString = csvContent.map((row) => row.join(",")).join("\n");
      
        // Create a Blob and download link for the CSV
        const blob = new Blob([csvString], { type: "text/csv" });
        const url = URL.createObjectURL(blob);
      
        // Create a link, trigger the download, and clean up
        const link = document.createElement("a");
        link.href = url;
        link.download = "chartData_y_values.csv";
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      };
  
      useEffect(() => {
        if (dataBuffer && dataBuffer.length >= 30) {
          console.log("Buffer reached 10, processing data");
  
          // Update the count of data points received
          const newCount = dataPointCount + dataBuffer.length;
          setDataPointCount(newCount);
          onDataPointCountChange(newCount);
  
          // Calculate the average of data1 and data2 from the buffer
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
  
          console.log(data1Avg, data2Avg);
  
          // Update chartData with new points, and ensure data arrays exist
          setChartData((prev) => [
            {
              ...prev[0],
              data: [
                ...(prev[0].data || []),
                { x: prev[0].data.length + 1, y: data1Avg },
              ],
            },
            {
              ...prev[1],
              data: [
                ...(prev[1].data || []),
                { x: prev[1].data.length + 1, y: data2Avg },
              ],
            },
          ]);
  
          // Clear the data buffer
          setDataBuffer([]);
        }
      }, [dataBuffer, setDataBuffer, dataPointCount, onDataPointCountChange]);
  
      // Function to trigger the download of the chart as an image
      const downloadChart = () => {
        console.log("button clicked", chartRef);
        if (chartRef.current) {
          console.log("button clicked");
          html2canvas(chartRef.current).then((canvas) => {
            console.log("button clicked", chartRef.current);
            const link = document.createElement("a");
            link.download = "chart.png"; // Name of the image file
            link.href = canvas.toDataURL(); // Convert canvas to base64 URL
            link.click(); // Trigger download
          });
        }
      };
  
      // Expose the downloadChart function to the parent via ref
      useImperativeHandle(ref, () => ({
        downloadChart,
        downloadDataBufferAsCSV,
      }));
      return (
        <div ref={chartRef} style={{ width: "100%", height: "100%" }}>
          <ResponsiveLine
            data={chartData}
            theme={{
              axis: {
                domain: {
                  line: {
                    stroke: colors.grey[100],
                  },
                },
                legend: {
                  text: {
                    fill: colors.grey[100],
                  },
                },
                ticks: {
                  line: {
                    stroke: colors.grey[100],
                    strokeWidth: 1,
                  },
                  text: {
                    fill: colors.grey[100],
                  },
                },
              },
              legends: {
                text: {
                  fill: colors.grey[100],
                },
              },
              tooltip: {
                container: {
                  color: colors.primary[500],
                },
              },
            }}
            colors={isDashboard ? { datum: "color" } : { scheme: "nivo" }}
            margin={{ top: 50, right: 110, bottom: 50, left: 60 }}
            xScale={{ type: "point" }}
            yScale={{
              type: "linear",
              min: "auto",
              max: "auto",
              stacked: false,
              reverse: false,
            }}
            curve="catmullRom"
            axisTop={null}
            axisRight={null}
            axisBottom={{
              orient: "bottom",
              tickSize: 0,
              tickPadding: 5,
              tickRotation: 0,
              legend: isDashboard ? undefined : "Data Points",
              legendOffset: 36,
              legendPosition: "middle",
            }}
            axisLeft={{
              orient: "left",
              tickValues: 5,
              tickSize: 3,
              tickPadding: 5,
              tickRotation: 0,
              legend: isDashboard ? undefined : "Value",
              legendOffset: -40,
              legendPosition: "middle",
            }}
            enableGridX={false}
            enableGridY={false}
            pointSize={1}
            pointColor={{ theme: "background" }}
            pointBorderWidth={2}
            pointBorderColor={{ from: "serieColor" }}
            pointLabelYOffset={-12}
            useMesh={true}
            legends={[
              {
                anchor: "bottom-right",
                direction: "column",
                justify: false,
                translateX: 100,
                translateY: 0,
                itemsSpacing: 0,
                itemDirection: "left-to-right",
                itemWidth: 80,
                itemHeight: 20,
                itemOpacity: 0.75,
                symbolSize: 12,
                symbolShape: "circle",
                symbolBorderColor: "rgba(0, 0, 0, .5)",
                effects: [
                  {
                    on: "hover",
                    style: {
                      itemBackground: "rgba(0, 0, 0, .03)",
                      itemOpacity: 1,
                    },
                  },
                ],
              },
            ]}
          />
        </div>
      );
    }
  );
  
  export default LineChart