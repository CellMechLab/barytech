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

const LineChart = forwardRef(({ dataset = "force" }, ref) => {
  const theme = useTheme();
  const colors = tokens(theme.palette.mode);
  console.log("theme:", theme, "colors:", colors, "dataset:", dataset);
  const chartRef = useRef(null);
  const { dataBuffer } = useContext(WebSocketContext);

  const transformData = (dataBuffer) => {
    const aggregatedData = {};
    dataBuffer.forEach((item) => {
      const timestamp = Math.floor(new Date(item.timestamp).getTime() / 1000);
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
        value: values.data1.reduce((a, b) => a + b, 0) / values.data1.length,
      });
      series2.push({
        date,
        value: values.data2.reduce((a, b) => a + b, 0) / values.data2.length,
      });
    });
    return { series1, series2 };
  };

  const downloadDataBufferAsCSV = () => {
    if (!dataBuffer || dataBuffer.length === 0) {
      alert("No data available to download.");
      return;
    }

    const { series1, series2 } = transformData(dataBuffer);
    const csvContent = [["Timestamp", "Displacement_Avg", "Force_Avg"]];
    const maxLength = Math.max(series1.length, series2.length);
    for (let i = 0; i < maxLength; i++) {
      const timestamp =
        series1[i]?.date.toISOString() || series2[i]?.date.toISOString() || "";
      const data1Avg = series1[i]?.value || "";
      const data2Avg = series2[i]?.value || "";
      csvContent.push([timestamp, data1Avg, data2Avg]);
    }

    const csvString = csvContent.map((row) => row.join(",")).join("\n");
    const blob = new Blob([csvString], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
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
        link.download = `${dataset}_chart.png`;
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
    const container = chartRef.current;
    const drawChart = () => {
      const containerWidth = container.offsetWidth;
      const containerHeight = container.offsetHeight;

      const margin = { top: 20, right: 30, bottom: 40, left: 60 };
      const chartWidth = containerWidth - margin.left - margin.right;
      const chartHeight = containerHeight - margin.top - margin.bottom - 50;
      d3.select(chartRef.current).selectAll("*").remove();

      const data = transformData(dataBuffer);
      const { series1, series2 } = data;
      const series = dataset === "force" ? series2 : series1;

      const navHeight = 50;

      const defaultXDomain = [
        new Date(),
        new Date(Date.now() + 60 * 60 * 1000),
      ];
      const defaultYDomain = dataset === "force" ? [-1e-6, 1e-6] : [-1e-12, 1e-12];

      const xDomain = series.length
        ? d3.extent(series, (d) => d.date)
        : defaultXDomain;

      const yDomain = series.length
        ? d3.extent(series, (d) => d.value)
        : defaultYDomain;
      const yPadding = (yDomain[1] - yDomain[0]) * 0.2 || (dataset === "force" ? 1e-7 : 1e-13);
      const yDomainPadded = [yDomain[0] - yPadding, yDomain[1] + yPadding];

      console.log("domains", xDomain, yDomainPadded);

      const x = d3.scaleTime().domain(xDomain).range([0, chartWidth]).nice();
      const y = d3.scaleLinear().domain(yDomainPadded).range([chartHeight, 0]).nice();

      const xNav = d3.scaleTime().domain(x.domain()).range([0, chartWidth]);
      const yNav = d3.scaleLinear().domain(y.domain()).range([navHeight, 0]);

      const svg = d3
        .select(chartRef.current)
        .append("svg")
        .attr("width", containerWidth)
        .attr("height", chartHeight + margin.top + margin.bottom + navHeight);

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
          `translate(${margin.left},${chartHeight + margin.top})`
        );

      const line = d3
        .line()
        .x((d) => x(d.date))
        .y((d) => y(d.value));

      linesGroup
        .append("path")
        .datum(series)
        .attr("class", `line line-${dataset}`)
        .attr("d", line)
        .attr("stroke", dataset === "force" ? "#FF9800" : "#009688")
        .attr("fill", "none");

      const circles = linesGroup
        .selectAll(`.point-${dataset}`)
        .data(series)
        .enter()
        .append("circle")
        .attr("class", `point-${dataset}`)
        .attr("cx", (d) => x(d.date))
        .attr("cy", (d) => y(d.value))
        .attr("r", 4)
        .attr("fill", dataset === "force" ? "#FF9800" : "#009688")
        .on("mouseover", (event, d) => showTooltip(event, d, dataset === "force" ? "Force" : "Displacement"))
        .on("mousemove", moveTooltip)
        .on("mouseout", hideTooltip);

      const tooltip = d3
        .select(chartRef.current)
        .append("div")
        .attr("class", `tooltip tooltip-${dataset}`)
        .style("position", "absolute")
        .style("display", "none")
        .style("padding", "6px")
        .style("background-color", colors.grey?.[100] || "white")
        .style("border", `1px solid ${colors.grey?.[500] || "#ccc"}`)
        .style("border-radius", "4px")
        .style("font-size", "12px")
        .style("color", colors.grey?.[900] || "#333")
        .style("pointer-events", "none");

      function showTooltip(event, d, label) {
        tooltip
          .html(
            `${label}<br>Date: ${d3.timeFormat("%Y-%m-%d %H:%M:%S")(
              d.date
            )}<br>Value: ${d.value.toExponential(2)} ${label === "Force" ? "N" : "m"}`
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

      const xAxis = chartGroup
        .append("g")
        .attr("class", "x-axis")
        .attr("transform", `translate(0,${chartHeight})`)
        .call(d3.axisBottom(x).ticks(10).tickFormat(d3.timeFormat("%H:%M:%S")))
        .append("text")
        .attr("x", chartWidth / 2)
        .attr("y", 35)
        .attr("fill", colors.grey?.[900] || "#333")
        .attr("text-anchor", "middle")
        .text("Time");

      const yAxis = chartGroup
        .append("g")
        .attr("class", "y-axis")
        .call(
          d3
            .axisLeft(y)
            .ticks(10)
            .tickFormat((d) => d.toExponential(2))
        )
        .append("text")
        .attr("x", -chartHeight / 2)
        .attr("y", -40)
        .attr("fill", colors.grey?.[900] || "#333")
        .attr("text-anchor", "middle")
        .attr("transform", "rotate(-90)")
        .text(dataset === "force" ? "Force (N)" : "Displacement (m)");

      const navLine = d3
        .line()
        .x((d) => xNav(d.date))
        .y((d) => yNav(d.value));

      navGroup
        .append("path")
        .datum(series)
        .attr("class", "line")
        .attr("d", navLine)
        .attr("stroke", dataset === "force" ? "#FF9800" : "#009688")
        .attr("fill", "none");

      let brushGroup;
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

      function updateHandles(selection) {
        if (!isBrushInitialized) return;
        if (selection) {
          const handleSize = 15;
          const handleColor = colors.grey?.[700] || "#546E7A";

          const handles = brushGroup
            .selectAll(".handle")
            .data([{ type: "w" }, { type: "e" }]);

          handles
            .enter()
            .append("rect")
            .attr("class", "handle")
            .attr("width", handleSize)
            .attr("height", navHeight)
            .style("fill", handleColor)
            .style("stroke", colors.grey?.[900] || "black")
            .style("stroke-width", 1)
            .attr("rx", 4)
            .attr("ry", 4)
            .merge(handles)
            .attr("x", (d, i) => selection[i] - handleSize / 2)
            .attr("y", 0)
            .style("fill", handleColor)
            .style("stroke", colors.grey?.[900] || "black")
            .style("stroke-width", 1)
            .attr("rx", 4)
            .attr("ry", 4)
            .on("mouseover", function () {
              d3.select(this).style("fill", colors.grey?.[500] || "#78909C");
            })
            .on("mouseout", function () {
              d3.select(this).style("fill", handleColor);
            });
          handles.exit().remove();
        }
      }

      function brushed(event) {
        const selection = event.selection;
        if (selection) {
          const [x0, x1] = selection.map(xNav.invert);
          x.domain([x0, x1]);

          const filteredSeries = series.filter(
            (d) => d.date >= x0 && d.date <= x1
          );

          y.domain([
            d3.min(filteredSeries, (d) => d.value) - yPadding,
            d3.max(filteredSeries, (d) => d.value) + yPadding,
          ]).nice();

          linesGroup.select(`.line-${dataset}`).attr("d", line);

          circles
            .attr("cx", (d) => x(d.date))
            .attr("cy", (d) => y(d.value));

          xAxis.call(
            d3.axisBottom(x).ticks(10).tickFormat(d3.timeFormat("%H:%M:%S"))
          );
          yAxis.call(
            d3
              .axisLeft(y)
              .ticks(10)
              .tickFormat((d) => d.toExponential(2))
          );

          updateHandles(selection);
        }
      }

      isBrushInitialized = true;
      updateHandles(x.range());
    };

    drawChart();
    const resizeObserver = new ResizeObserver(() => {
      drawChart();
    });
    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, [dataBuffer, dataset]);

  return <div ref={chartRef} style={{ position: "relative", height: "400px" }} />;
});

export default LineChart;