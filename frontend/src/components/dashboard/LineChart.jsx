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

const FORCE_UNIT = process.env.REACT_APP_FORCE_UNIT || "N";
const FALLBACK_SAMPLE_INTERVAL_MS = Math.max(
  Number(process.env.REACT_APP_CHART_SAMPLE_INTERVAL_MS) || 1,
  Number.EPSILON
);
const LineChart = forwardRef(({ dataset = "force" }, ref) => {
  const theme = useTheme();
  const colors = tokens(theme.palette.mode);
  const chartRef = useRef(null);
  const { dataBuffer } = useContext(WebSocketContext);

  const parseTimestampMs = (timestamp, index) => {
    const numericTimestamp =
      typeof timestamp === "number" ||
      (typeof timestamp === "string" && timestamp.trim() !== "")
        ? Number(timestamp)
        : NaN;

    if (Number.isFinite(numericTimestamp)) {
      return Math.abs(numericTimestamp) > 1e12
        ? numericTimestamp
        : numericTimestamp * 1000;
    }

    const parsedMs = new Date(timestamp).getTime();
    if (!Number.isFinite(parsedMs)) {
      return index;
    }

    const fractionalMatch = String(timestamp).match(/\.(\d+)(?=Z|[+-]\d{2}:?\d{2}|$)/);
    if (!fractionalMatch) {
      return parsedMs;
    }

    const baseSecondMs = parsedMs - (parsedMs % 1000);
    const fractionalMs = Number(`0.${fractionalMatch[1]}`) * 1000;
    return baseSecondMs + fractionalMs;
  };

  const formatTimestamp = (xValue) => {
    const date = new Date(Math.floor(xValue));
    const baseTime = d3.timeFormat("%H:%M:%S.%L")(date);
    const microseconds = Math.floor((xValue - Math.floor(xValue)) * 1000);
    return microseconds > 0
      ? `${baseTime}${String(microseconds).padStart(3, "0")}`
      : baseTime;
  };

  const hasHighResolutionTimestamp = (item, timestamp) => {
    if (item.timestamp_ms != null) {
      return true;
    }

    const numericTimestamp = Number(timestamp);
    if (Number.isFinite(numericTimestamp)) {
      return Math.abs(numericTimestamp) > 1e12;
    }

    return /\.\d+(?=Z|[+-]\d{2}:?\d{2}|$)/.test(String(timestamp));
  };

  const resolvePlotXValues = (dataBuffer) => {
    const points = dataBuffer.map((item, index) => {
      const timestamp =
        item.timestamp_ms ?? item.timestamp ?? item.time ?? item.t;
      const sampleIndex = Number(item.sample_index);

      return {
        index,
        sampleIndex: Number.isFinite(sampleIndex) ? sampleIndex : index,
        timestamp,
        rawXValue: parseTimestampMs(timestamp, index),
        hasHighResolutionTimestamp: hasHighResolutionTimestamp(item, timestamp),
      };
    });

    const xValues = new Array(points.length);
    let groupStart = 0;

    while (groupStart < points.length) {
      let groupEnd = groupStart + 1;
      while (
        groupEnd < points.length &&
        points[groupEnd].rawXValue === points[groupStart].rawXValue
      ) {
        groupEnd += 1;
      }

      const group = points
        .slice(groupStart, groupEnd)
        .sort((a, b) => a.sampleIndex - b.sampleIndex);
      const nextXValue = points[groupEnd]?.rawXValue;
      const availableWindow =
        Number.isFinite(nextXValue) && nextXValue > group[0].rawXValue
          ? nextXValue - group[0].rawXValue
          : FALLBACK_SAMPLE_INTERVAL_MS * group.length;
      const sampleInterval = availableWindow / group.length;

      group.forEach((point, offset) => {
        xValues[point.index] = point.rawXValue + offset * sampleInterval;
      });

      groupStart = groupEnd;
    }

    return { points, xValues };
  };

  const transformData = (dataBuffer) => {
    const series1 = [];
    const series2 = [];
    const { points, xValues } = resolvePlotXValues(dataBuffer);
    const latestPoint = points[points.length - 1];
    const shouldDeferLatestGroup =
      latestPoint && !latestPoint.hasHighResolutionTimestamp;

    dataBuffer.forEach((item, index) => {
      const timestamp =
        item.timestamp_ms ?? item.timestamp ?? item.time ?? item.t;
      const xValue = xValues[index];
      const displacement =
        item.displacement == null ? NaN : Number(item.displacement);
      const force = item.force == null ? NaN : Number(item.force);

      if (Number.isFinite(displacement)) {
        series1.push({
          date: new Date(Math.floor(xValue)),
          xValue,
          timestamp,
          value: displacement,
          isStable:
            !shouldDeferLatestGroup ||
            points[index].rawXValue !== latestPoint.rawXValue,
        });
      }

      if (Number.isFinite(force)) {
        series2.push({
          date: new Date(Math.floor(xValue)),
          xValue,
          timestamp,
          value: force,
          isStable:
            !shouldDeferLatestGroup ||
            points[index].rawXValue !== latestPoint.rawXValue,
        });
      }
    });

    series1.sort((a, b) => a.xValue - b.xValue);
    series2.sort((a, b) => a.xValue - b.xValue);

    return { series1, series2 };
  };

  const downloadDataBufferAsCSV = () => {
    if (!dataBuffer || dataBuffer.length === 0) {
      alert("No data available to download.");
      return;
    }

    const csvContent = [["Timestamp", "Displacement", `Force (${FORCE_UNIT})`]];
    dataBuffer.forEach((item) => {
      csvContent.push([
        item.timestamp_ms ?? item.timestamp ?? "",
        item.displacement ?? "",
        item.force ?? "",
      ]);
    });

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
      const fullSeries = dataset === "force" ? series2 : series1;
      const series = fullSeries.filter((point) => point.isStable);

      const navHeight = 50;

      const defaultXDomain = [Date.now(), Date.now() + 60 * 60 * 1000];
      const defaultYDomain = dataset === "force" ? [-1e-6, 1e-6] : [-1e-12, 1e-12];

      const xDomain = series.length
        ? d3.extent(series, (d) => d.xValue)
        : defaultXDomain;

      const yDomain = series.length
        ? d3.extent(series, (d) => d.value)
        : defaultYDomain;
      const yPadding = (yDomain[1] - yDomain[0]) * 0.2 || (dataset === "force" ? 1e-7 : 1e-13);
      const yDomainPadded = [yDomain[0] - yPadding, yDomain[1] + yPadding];

      const x = d3.scaleLinear().domain(xDomain).range([0, chartWidth]).nice();
      const y = d3.scaleLinear().domain(yDomainPadded).range([chartHeight, 0]).nice();

      const xNav = d3.scaleLinear().domain(x.domain()).range([0, chartWidth]);
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
        .x((d) => x(d.xValue))
        .y((d) => y(d.value));

      linesGroup
        .append("path")
        .datum(series)
        .attr("class", `line line-${dataset}`)
        .attr("d", line)
        .attr("stroke", dataset === "force" ? "#FF9800" : "#009688")
        .attr("fill", "none");

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
            `${label}<br>Time: ${d.timestamp || formatTimestamp(d.xValue)}<br>Value: ${d.value.toExponential(2)} ${label === "Force" ? FORCE_UNIT : "m"}`
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

      const showPointMarkers = series.length <= 1000;
      const circles = showPointMarkers
        ? linesGroup
            .selectAll(`.point-${dataset}`)
            .data(series)
            .enter()
            .append("circle")
            .attr("class", `point-${dataset}`)
            .attr("cx", (d) => x(d.xValue))
            .attr("cy", (d) => y(d.value))
            .attr("r", 4)
            .attr("fill", dataset === "force" ? "#FF9800" : "#009688")
            .on("mouseover", (event, d) => showTooltip(event, d, dataset === "force" ? "Force" : "Displacement"))
            .on("mousemove", moveTooltip)
            .on("mouseout", hideTooltip)
        : linesGroup.selectAll(`.point-${dataset}`);

      const xAxisGroup = chartGroup
        .append("g")
        .attr("class", "x-axis")
        .attr("transform", `translate(0,${chartHeight})`)
        .call(d3.axisBottom(x).ticks(10).tickFormat(formatTimestamp));

      xAxisGroup
        .append("text")
        .attr("x", chartWidth / 2)
        .attr("y", 35)
        .attr("fill", colors.grey?.[900] || "#333")
        .attr("text-anchor", "middle")
        .text("Time");

      const yAxisGroup = chartGroup
        .append("g")
        .attr("class", "y-axis")
        .call(
          d3
            .axisLeft(y)
            .ticks(10)
            .tickFormat((d) => d.toExponential(2))
        );

      yAxisGroup
        .append("text")
        .attr("x", -chartHeight / 2)
        .attr("y", -40)
        .attr("fill", colors.grey?.[900] || "#333")
        .attr("text-anchor", "middle")
        .attr("transform", "rotate(-90)")
        .text(dataset === "force" ? `Force (${FORCE_UNIT})` : "Displacement (m)");

      const navLine = d3
        .line()
        .x((d) => xNav(d.xValue))
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
            (d) => d.xValue >= x0 && d.xValue <= x1
          );

          if (filteredSeries.length) {
            y.domain([
              d3.min(filteredSeries, (d) => d.value) - yPadding,
              d3.max(filteredSeries, (d) => d.value) + yPadding,
            ]).nice();
          }

          linesGroup.select(`.line-${dataset}`).attr("d", line);

          circles
            .attr("cx", (d) => x(d.xValue))
            .attr("cy", (d) => y(d.value));

          xAxisGroup.call(d3.axisBottom(x).ticks(10).tickFormat(formatTimestamp));
          yAxisGroup.call(
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
