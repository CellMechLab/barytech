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

// Display unit for force on live charts (μN = micro-Newtons).
const FORCE_UNIT = process.env.REACT_APP_FORCE_UNIT || "μN";
// Display unit for Z/displacement on live charts.
const DISPLACEMENT_UNIT = process.env.REACT_APP_DISPLACEMENT_UNIT || "μm";
// Scale factors from raw SI telemetry (m, N) to chart display units.
const METERS_TO_MICROMETERS = 1e6;
const NEWTONS_TO_MICRONEWTONS = 1e6;
const FALLBACK_SAMPLE_INTERVAL_MS = Math.max(
  Number(process.env.REACT_APP_CHART_SAMPLE_INTERVAL_MS) || 1,
  Number.EPSILON
);
// Minimum ms between chart redraws (~4 fps default; 500 ms ≈ 2 fps).
const CHART_REDRAW_INTERVAL_MS = Math.max(
  Number(process.env.REACT_APP_CHART_REDRAW_INTERVAL_MS) || 250,
  50
);

// Formats Y-axis and tooltip values with fixed decimals or scientific notation.
const formatChartValue = (value) => {
  const abs = Math.abs(value);
  if (!Number.isFinite(value)) return "—";
  if (abs === 0) return "0";
  return abs >= 0.01 ? value.toFixed(3) : value.toExponential(2);
};
const LineChart = forwardRef(({ dataset = "force" }, ref) => {
  const theme = useTheme();
  const colors = tokens(theme.palette.mode);
  const chartRef = useRef(null);
  const { dataBuffer } = useContext(WebSocketContext);
  // Holds latest props so resize redraws do not need to recreate the observer.
  const dataBufferRef = useRef(dataBuffer);
  const datasetRef = useRef(dataset);
  const colorsRef = useRef(colors);
  // Tracks last rendered size to skip redundant resize redraws.
  const lastDrawnSizeRef = useRef({ width: 0, height: 0 });
  // Pending animation frame id for debounced resize handling.
  const resizeFrameRef = useRef(null);
  // Timestamp of the last completed data-driven chart redraw.
  const lastChartRedrawMsRef = useRef(0);
  // Pending rAF id for a throttled data-buffer redraw.
  const pendingDataRedrawFrameRef = useRef(null);
  // Pending timeout that fires when the throttle window has elapsed.
  const pendingDataRedrawTimeoutRef = useRef(null);
  // Unique SVG clip-path id so multiple charts on the dashboard do not clash.
  const clipIdRef = useRef(`clip-${Math.random().toString(36).slice(2, 9)}`);

  dataBufferRef.current = dataBuffer;
  datasetRef.current = dataset;
  colorsRef.current = colors;

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
          value: force * NEWTONS_TO_MICRONEWTONS,
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

    const csvContent = [["Timestamp", `Z (${DISPLACEMENT_UNIT})`, `Force (${FORCE_UNIT})`]];
    dataBuffer.forEach((item) => {
      const displacement = item.displacement == null ? "" : Number(item.displacement);
      const force = item.force == null ? "" : Number(item.force);
      csvContent.push([
        item.timestamp_ms ?? item.timestamp ?? "",
        Number.isFinite(displacement) ? displacement * METERS_TO_MICROMETERS : "",
        Number.isFinite(force) ? force * NEWTONS_TO_MICRONEWTONS : "",
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

  // Stable draw function reference for the resize observer effect.
  const drawChartRef = useRef(() => {});

  useEffect(() => {
    const container = chartRef.current;
    if (!container) return undefined;

    const drawChart = () => {
      const containerWidth = container.offsetWidth;
      const containerHeight = container.offsetHeight;
      if (containerWidth <= 0 || containerHeight <= 0) return;

      lastDrawnSizeRef.current = { width: containerWidth, height: containerHeight };

      const activeDataset = datasetRef.current;
      const activeColors = colorsRef.current;
      const activeDataBuffer = dataBufferRef.current;
      const clipId = clipIdRef.current;

      // Extra left margin so the rotated Y-axis unit label is not clipped.
      const margin = { top: 20, right: 30, bottom: 40, left: 78 };
      const chartWidth = Math.max(containerWidth - margin.left - margin.right, 0);
      const chartHeight = Math.max(containerHeight - margin.top - margin.bottom - 50, 0);
      // Axis text color — grey[100] stays readable on the dark dashboard cards.
      const axisTextColor = activeColors.grey?.[100] || "#e0e0e0";
      const axisLineColor = activeColors.grey?.[400] || "#858585";
      d3.select(chartRef.current).selectAll("*").remove();

      const data = transformData(activeDataBuffer);
      const { series1, series2 } = data;
      const fullSeries = activeDataset === "force" ? series2 : series1;
      const series = fullSeries.filter((point) => point.isStable);

      const navHeight = 50;

      const defaultXDomain = [Date.now(), Date.now() + 60 * 60 * 1000];
      const defaultYDomain = activeDataset === "force" ? [-1, 1] : [-2, 0];

      const xDomain = series.length
        ? d3.extent(series, (d) => d.xValue)
        : defaultXDomain;

      const yDomain = series.length
        ? d3.extent(series, (d) => d.value)
        : defaultYDomain;
      const yPadding = (yDomain[1] - yDomain[0]) * 0.2 || 0.1;
      const yDomainPadded = [yDomain[0] - yPadding, yDomain[1] + yPadding];

      const x = d3.scaleLinear().domain(xDomain).range([0, chartWidth]).nice();
      const y = d3.scaleLinear().domain(yDomainPadded).range([chartHeight, 0]).nice();

      const xNav = d3.scaleLinear().domain(x.domain()).range([0, chartWidth]);
      const yNav = d3.scaleLinear().domain(y.domain()).range([navHeight, 0]);

      const svg = d3
        .select(chartRef.current)
        .append("svg")
        .attr("width", containerWidth)
        .attr("height", containerHeight)
        .attr("style", "display: block; overflow: visible;");

      svg
        .append("defs")
        .append("clipPath")
        .attr("id", clipId)
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

      const linesGroup = chartGroup.append("g").attr("clip-path", `url(#${clipId})`);

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
        .attr("class", `line line-${activeDataset}`)
        .attr("d", line)
        .attr("stroke", activeDataset === "force" ? "#FF9800" : "#009688")
        .attr("fill", "none");

      const tooltip = d3
        .select(chartRef.current)
        .append("div")
        .attr("class", `tooltip tooltip-${activeDataset}`)
        .style("position", "absolute")
        .style("display", "none")
        .style("padding", "6px")
        .style("background-color", activeColors.grey?.[100] || "white")
        .style("border", `1px solid ${activeColors.grey?.[500] || "#ccc"}`)
        .style("border-radius", "4px")
        .style("font-size", "12px")
        .style("color", activeColors.grey?.[900] || "#333")
        .style("pointer-events", "none");

      function showTooltip(event, d, label) {
        const unit = label === "Force" ? FORCE_UNIT : DISPLACEMENT_UNIT;
        tooltip
          .html(
            `${label}<br>Time: ${d.timestamp || formatTimestamp(d.xValue)}<br>Value: ${formatChartValue(d.value)} ${unit}`
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
            .selectAll(`.point-${activeDataset}`)
            .data(series)
            .enter()
            .append("circle")
            .attr("class", `point-${activeDataset}`)
            .attr("cx", (d) => x(d.xValue))
            .attr("cy", (d) => y(d.value))
            .attr("r", 4)
            .attr("fill", activeDataset === "force" ? "#FF9800" : "#009688")
            .on("mouseover", (event, d) => showTooltip(event, d, activeDataset === "force" ? "Force" : "Z"))
            .on("mousemove", moveTooltip)
            .on("mouseout", hideTooltip)
        : linesGroup.selectAll(`.point-${activeDataset}`);

      const xAxisGroup = chartGroup
        .append("g")
        .attr("class", "x-axis")
        .attr("transform", `translate(0,${chartHeight})`)
        .call(d3.axisBottom(x).ticks(10).tickFormat(formatTimestamp));

      xAxisGroup.selectAll(".tick text").attr("fill", axisTextColor);
      xAxisGroup.selectAll(".tick line, .domain").attr("stroke", axisLineColor);

      xAxisGroup
        .append("text")
        .attr("class", "x-axis-label")
        .attr("x", chartWidth / 2)
        .attr("y", 35)
        .attr("fill", axisTextColor)
        .attr("text-anchor", "middle")
        .text("Time");

      const yAxisGroup = chartGroup
        .append("g")
        .attr("class", "y-axis")
        .call(
          d3
            .axisLeft(y)
            .ticks(10)
            .tickFormat((d) => formatChartValue(d))
        );

      yAxisGroup.selectAll(".tick text").attr("fill", axisTextColor);
      yAxisGroup.selectAll(".tick line, .domain").attr("stroke", axisLineColor);

      yAxisGroup
        .append("text")
        .attr("class", "y-axis-label")
        .attr("transform", "rotate(-90)")
        .attr("y", 0 - margin.left + 18)
        .attr("x", 0 - chartHeight / 2)
        .attr("fill", axisTextColor)
        .attr("text-anchor", "middle")
        .text(activeDataset === "force" ? `Force (${FORCE_UNIT})` : `Z (${DISPLACEMENT_UNIT})`);

      const navLine = d3
        .line()
        .x((d) => xNav(d.xValue))
        .y((d) => yNav(d.value));

      navGroup
        .append("path")
        .datum(series)
        .attr("class", "line")
        .attr("d", navLine)
        .attr("stroke", activeDataset === "force" ? "#FF9800" : "#009688")
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
          const handleColor = activeColors.grey?.[700] || "#546E7A";

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
            .style("stroke", activeColors.grey?.[900] || "black")
            .style("stroke-width", 1)
            .attr("rx", 4)
            .attr("ry", 4)
            .merge(handles)
            .attr("x", (d, i) => selection[i] - handleSize / 2)
            .attr("y", 0)
            .style("fill", handleColor)
            .style("stroke", activeColors.grey?.[900] || "black")
            .style("stroke-width", 1)
            .attr("rx", 4)
            .attr("ry", 4)
            .on("mouseover", function () {
              d3.select(this).style("fill", activeColors.grey?.[500] || "#78909C");
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

          linesGroup.select(`.line-${activeDataset}`).attr("d", line);

          circles
            .attr("cx", (d) => x(d.xValue))
            .attr("cy", (d) => y(d.value));

          xAxisGroup.call(d3.axisBottom(x).ticks(10).tickFormat(formatTimestamp));
          xAxisGroup.selectAll(".tick text").attr("fill", axisTextColor);
          xAxisGroup.selectAll(".tick line, .domain").attr("stroke", axisLineColor);
          yAxisGroup.call(
            d3
              .axisLeft(y)
              .ticks(10)
              .tickFormat((d) => formatChartValue(d))
          );
          yAxisGroup.selectAll(".tick text").attr("fill", axisTextColor);
          yAxisGroup.selectAll(".tick line, .domain").attr("stroke", axisLineColor);

          updateHandles(selection);
        }
      }

      isBrushInitialized = true;
      updateHandles(x.range());
    };

    drawChartRef.current = drawChart;
    drawChart();
  }, [dataset, theme.palette.mode]);

  useEffect(() => {
    // Schedules a redraw at most every CHART_REDRAW_INTERVAL_MS using rAF + skip.
    const scheduleThrottledDataRedraw = () => {
      const runRedraw = () => {
        pendingDataRedrawFrameRef.current = null;
        lastChartRedrawMsRef.current = performance.now();
        drawChartRef.current();
      };

      const now = performance.now();
      const elapsed = now - lastChartRedrawMsRef.current;

      if (elapsed >= CHART_REDRAW_INTERVAL_MS) {
        if (pendingDataRedrawTimeoutRef.current !== null) {
          window.clearTimeout(pendingDataRedrawTimeoutRef.current);
          pendingDataRedrawTimeoutRef.current = null;
        }
        if (pendingDataRedrawFrameRef.current !== null) {
          cancelAnimationFrame(pendingDataRedrawFrameRef.current);
        }
        pendingDataRedrawFrameRef.current = requestAnimationFrame(runRedraw);
        return;
      }

      if (
        pendingDataRedrawTimeoutRef.current !== null ||
        pendingDataRedrawFrameRef.current !== null
      ) {
        return;
      }

      pendingDataRedrawTimeoutRef.current = window.setTimeout(() => {
        pendingDataRedrawTimeoutRef.current = null;
        pendingDataRedrawFrameRef.current = requestAnimationFrame(runRedraw);
      }, CHART_REDRAW_INTERVAL_MS - elapsed);
    };

    scheduleThrottledDataRedraw();

    return () => {
      if (pendingDataRedrawTimeoutRef.current !== null) {
        window.clearTimeout(pendingDataRedrawTimeoutRef.current);
        pendingDataRedrawTimeoutRef.current = null;
      }
      if (pendingDataRedrawFrameRef.current !== null) {
        cancelAnimationFrame(pendingDataRedrawFrameRef.current);
        pendingDataRedrawFrameRef.current = null;
      }
    };
  }, [dataBuffer]);

  useEffect(() => {
    const container = chartRef.current;
    if (!container) return undefined;

    // Debounce resize redraws to avoid ResizeObserver feedback loops in CRA overlay.
    const scheduleResizeDraw = () => {
      if (resizeFrameRef.current !== null) {
        cancelAnimationFrame(resizeFrameRef.current);
      }
      resizeFrameRef.current = requestAnimationFrame(() => {
        resizeFrameRef.current = null;
        const width = container.offsetWidth;
        const height = container.offsetHeight;
        const last = lastDrawnSizeRef.current;
        if (width === last.width && height === last.height) return;
        drawChartRef.current();
      });
    };

    const resizeObserver = new ResizeObserver(scheduleResizeDraw);
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      if (resizeFrameRef.current !== null) {
        cancelAnimationFrame(resizeFrameRef.current);
        resizeFrameRef.current = null;
      }
    };
  }, []);

  return (
    <div
      ref={chartRef}
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        minHeight: "120px",
        overflow: "hidden",
      }}
    />
  );
});

export default LineChart;
