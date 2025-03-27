import React, {
  useEffect,
  useRef,
  useContext,
  forwardRef,
  useImperativeHandle,
} from "react";
import * as d3 from "d3";
import { WebSocketContext } from "./WebSocketProvider";
import html2canvas from "html2canvas";
import { useTheme } from "@mui/material";
import { tokens } from "../../theme";

const LineChart = forwardRef((props, ref) => {
  const theme = useTheme();
  const colors = tokens(theme.palette.mode);
  const chartRef = useRef(null);
  const { dataBuffer } = useContext(WebSocketContext);

  const transformData = (dataBuffer) => {
    const aggregatedData = {}; // For grouping and aggregation by second

    dataBuffer.forEach((item) => {
      const timestamp = Math.floor(new Date(item.timestamp).getTime() / 1000); // Group by second
      if (!aggregatedData[timestamp]) {
        aggregatedData[timestamp] = { data1: [], data2: [] };
      }
      aggregatedData[timestamp].data1.push(item.displacement);
      aggregatedData[timestamp].data2.push(item.force);
    });

    const series1 = [];
    const series2 = [];

    Object.entries(aggregatedData).forEach(([timestamp, values]) => {
      const date = new Date(timestamp * 1000);
      series1.push({
        date,
        value: values.data1.reduce((a, b) => a + b, 0) / values.data1.length, // Average data1
      });
      series2.push({
        date,
        value: values.data2.reduce((a, b) => a + b, 0) / values.data2.length, // Average data2
      });
    });

    return { series1, series2 };
  };
  const downloadDataBufferAsCSV = () => {
    if (!dataBuffer || dataBuffer.length === 0) {
      alert("No data available to download.");
      return;
    }

    // Transform the data buffer into aggregated data
    const { series1, series2 } = transformData(dataBuffer);

    // Prepare CSV headers
    const csvContent = [["Timestamp", "Data1_Avg", "Data2_Avg"]];

    // Combine the two series into rows
    const maxLength = Math.max(series1.length, series2.length);
    for (let i = 0; i < maxLength; i++) {
      const timestamp =
        series1[i]?.date.toISOString() || series2[i]?.date.toISOString() || "";
      const data1Avg = series1[i]?.value || "";
      const data2Avg = series2[i]?.value || "";
      csvContent.push([timestamp, data1Avg, data2Avg]);
    }

    // Convert CSV content to a string
    const csvString = csvContent.map((row) => row.join(",")).join("\n");

    // Create a Blob from the CSV string
    const blob = new Blob([csvString], { type: "text/csv" });
    const url = URL.createObjectURL(blob);

    // Create a download link and trigger the download
    const link = document.createElement("a");
    link.href = url;
    link.download = "aggregated_data.csv";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };
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
    transformData,
  }));

  useEffect(() => {
    const container = chartRef.current; // Your chart container element
    const drawChart = () => {
      const containerWidth = container.offsetWidth;
      const containerHeight = container.offsetHeight;

      const margin = { top: 20, right: 30, bottom: 40, left: 50 };
      const chartWidth = containerWidth - margin.left - margin.right;
      const chartHeight = containerHeight - margin.top - margin.bottom - 50;
      d3.select(chartRef.current).selectAll("*").remove(); // Clear early

      const data = transformData(dataBuffer);
      const { series1, series2 } = data;

      const width = chartWidth; // Keep consistent
      const height = 400; // Ensure this aligns with chart dimensions
      const navHeight = 50;

      const defaultXDomain = [
        new Date(),
        new Date(Date.now() + 60 * 60 * 1000),
      ]; // Next hour
      const defaultYDomain = [0, 1000];

      const xDomain =
        series1.length || series2.length
          ? d3.extent([...series1, ...series2], (d) => d.date)
          : defaultXDomain;

      const yDomain =
        series1.length || series2.length ? [0, 1000] : defaultYDomain;
      const x = d3.scaleTime().domain(xDomain).range([0, chartWidth]);

      const y = d3.scaleLinear().domain(yDomain).range([chartHeight, 0]);

      const xNav = d3.scaleTime().domain(x.domain()).range([0, chartWidth]);
      const yNav = d3.scaleLinear().domain(y.domain()).range([navHeight, 0]);

      const svg = d3
        .select(chartRef.current)
        .append("svg")
        .attr("width", containerWidth)
        .attr("height", height);

      // Define a clipping path
      svg
        .append("defs")
        .append("clipPath")
        .attr("id", "clip")
        .append("rect")
        .attr("width", chartWidth + 5)
        .attr("height", chartHeight);

      const chartGroup = svg
        .append("g")
        .attr("transform", `translate(${margin.left},${margin.top})`);

      // Add horizontal grid lines
      chartGroup
        .selectAll(".grid-line")
        .data(y.ticks(10))
        .enter()
        .append("line")
        .attr("class", "grid-line")
        .attr("x1", 0)
        .attr("x2", chartWidth)
        .attr("y1", (d) => y(d))
        .attr("y2", (d) => y(d))
        .attr("stroke", "#ddd")
        .attr("stroke-dasharray", "2,2");

      const linesGroup = chartGroup.append("g").attr("clip-path", "url(#clip)");

      const navGroup = svg
        .append("g")
        .attr(
          "transform",
          `translate(${margin.left},${height - navHeight - margin.bottom})`
        );

      const line1 = d3
        .line()
        .x((d) => x(d.date))
        .y((d) => y(d.value));

      const line2 = d3
        .line()
        .x((d) => x(d.date))
        .y((d) => y(d.value));

      // Draw lines for each series in the linesGroup with clipping
      linesGroup
        .append("path")
        .datum(series1)
        .attr("class", "line line1")
        .attr("d", line1)
        .attr("stroke", "#009688")
        .attr("fill", "none");

      linesGroup
        .append("path")
        .datum(series2)
        .attr("class", "line line2")
        .attr("d", line2)
        .attr("stroke", "#FF9800")
        .attr("fill", "none");

      // Add circles for each data point on series1
      const circles1 = linesGroup
        .selectAll(".point1")
        .data(series1)
        .enter()
        .append("circle")
        .attr("class", "point1")
        .attr("cx", (d) => x(d.date))
        .attr("cy", (d) => y(d.value))
        .attr("r", 4)
        .attr("fill", "#009688")
        .on("mouseover", (event, d) => showTooltip(event, d, "Data1"))
        .on("mousemove", moveTooltip)
        .on("mouseout", hideTooltip);

      // Add circles for each data point on series2
      const circles2 = linesGroup
        .selectAll(".point2")
        .data(series2)
        .enter()
        .append("circle")
        .attr("class", "point2")
        .attr("cx", (d) => x(d.date))
        .attr("cy", (d) => y(d.value))
        .attr("r", 4)
        .attr("fill", "#FF9800")
        .on("mouseover", (event, d) => showTooltip(event, d, "Data2"))
        .on("mousemove", moveTooltip)
        .on("mouseout", hideTooltip);

      // Tooltip div
      const tooltip = d3
        .select(chartRef.current)
        .append("div")
        .attr("class", "tooltip")
        .style("position", "absolute")
        .style("display", "none") // Initially hidden
        .style("padding", "6px")
        .style("background-color", "white")
        .style("border", "1px solid #ccc")
        .style("border-radius", "4px")
        .style("font-size", "12px")
        .style("color", "#333")
        .style("pointer-events", "none")
        .style("width", "100px")
        .style("height", "100px");

      function showTooltip(event, d, label) {
        console.log("show");
        tooltip
          .html(
            `${label}<br>Date: ${d3.timeFormat("%Y-%m-%d %H:%M:%S")(
              d.date
            )}<br>Value: ${d.value}`
          )
          .style("display", "block");
      }

      function moveTooltip(event) {
        const containerPosition = chartRef.current.getBoundingClientRect();

        tooltip
          .style("top", `${event.clientY - containerPosition.top + 10}px`)
          .style("left", `${event.clientX - containerPosition.left + 10}px`);
      }

      function hideTooltip() {
        tooltip.style("display", "none");
      }

      // Add x-axis with ticks and labels in chartGroup (outside clipping)
      const xAxis = chartGroup
        .append("g")
        .attr("class", "x-axis")
        .attr("transform", `translate(0,${chartHeight})`)
        .call(d3.axisBottom(x).ticks(10).tickFormat(d3.timeFormat("%H:%M:%S")));

      // Add y-axis with ticks and labels in chartGroup (outside clipping)
      const yAxis = chartGroup
        .append("g")
        .attr("class", "y-axis")
        .call(d3.axisLeft(y).ticks(10));

      const navLine1 = d3
        .line()
        .x((d) => xNav(d.date))
        .y((d) => yNav(d.value));

      const navLine2 = d3
        .line()
        .x((d) => xNav(d.date))
        .y((d) => yNav(d.value));

      navGroup
        .append("path")
        .datum(series1)
        .attr("class", "line")
        .attr("d", navLine1)
        .attr("stroke", "lightgrey")
        .attr("fill", "none");

      navGroup
        .append("path")
        .datum(series2)
        .attr("class", "line")
        .attr("d", navLine2)
        .attr("stroke", "darkgrey")
        .attr("fill", "none");

      let brushGroup; // Declare brushGroup so it can be used in updateHandles and brushed
      let isBrushInitialized = false;
      const brush = d3
        .brushX()
        .extent([
          [0, 0],
          [chartWidth, navHeight],
        ])
        .on("brush end", brushed);

      brushGroup = navGroup
        .append("g")

        .attr("class", "brush")
        .call(brush)
        .call(brush.move, x.range());
      // console.log("X Range:", x.range(), chartWidth); // Should match [0, chartWidth]

      // Initialize handle positions
      function updateHandles(selection) {
        if (!isBrushInitialized) return;
        if (selection) {
          const handleSize = 15;
          const handleColor = "#546E7A";

          const handles = brushGroup
            .selectAll(".handle")
            .data([{ type: "w" }, { type: "e" }]);

          handles
            .enter()
            .append("rect")
            .attr("class", "handle")
            .attr("width", handleSize)
            .attr("height", navHeight)
            .style("fill", handleColor) // Using .style for CSS override
            // .style("stroke", "black") // Outline for visibility
            .style("stroke-width", 10)
            .attr("opacity", 1)
            .merge(handles)
            .attr("x", (d, i) => selection[i] - handleSize / 2)
            .attr("y", 0)
            .style("fill", handleColor)
            .style("stroke", "black") // Outline for visibility
            .style("stroke-width", 1)
            .attr("rx", 4) // Rounded corners
            .attr("ry", 4) // Rounded corners
            .on("mouseover", function () {
              d3.select(this).style("fill", "#78909C");
            })
            .on("mouseout", function () {
              d3.select(this).style("fill", handleColor);
            });
          handles.exit().remove();
        }
        // console.log("Handles updated at positions:", selection); // Debugging log
      }

      function brushed(event) {
        const selection = event.selection;
        if (selection) {
          const [x0, x1] = selection.map(xNav.invert);

          x.domain([x0, x1]);

          const filteredSeries1 = series1.filter(
            (d) => d.date >= x0 && d.date <= x1
          );
          const filteredSeries2 = series2.filter(
            (d) => d.date >= x0 && d.date <= x1
          );

          y.domain([
            0,
            d3.max([...filteredSeries1, ...filteredSeries2], (d) => d.value) +
              100,
          ]);

          linesGroup.select(".line1").attr("d", line1);
          linesGroup.select(".line2").attr("d", line2);

          // Update circles based on new scales
          circles1.attr("cx", (d) => x(d.date)).attr("cy", (d) => y(d.value));

          circles2.attr("cx", (d) => x(d.date)).attr("cy", (d) => y(d.value));

          // Update axes
          xAxis.call(
            d3.axisBottom(x).ticks(10).tickFormat(d3.timeFormat("%H:%M:%S"))
          );
          yAxis.call(d3.axisLeft(y).ticks(10));

          updateHandles(selection); // Update handle positions
        }
      }
      isBrushInitialized = true;
      // Add brush handles to visually indicate draggable areas
      updateHandles(x.range());
    };
    // Draw the chart initially
    drawChart();
    const resizeObserver = new ResizeObserver(() => {
      drawChart();
    });
    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, [dataBuffer]);

  return <div ref={chartRef} style={{ position: "relative" }}></div>;
});

export default LineChart;
