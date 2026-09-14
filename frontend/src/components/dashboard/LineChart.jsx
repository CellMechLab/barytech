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
import {
  DISPLACEMENT_UNIT,
  FORCE_UNIT,
  formatDisplacementMicrometers,
} from "../../config/units";

// Display units match values stored after MQTT normalization (µm, µN).
const FORCE_UNIT_LABEL = FORCE_UNIT;
const FALLBACK_SAMPLE_INTERVAL_MS = Math.max(
  Number(process.env.REACT_APP_CHART_SAMPLE_INTERVAL_MS) || 1,
  Number.EPSILON
);
// Minimum ms between chart redraws (~4 fps default; 500 ms ≈ 2 fps).
const CHART_REDRAW_INTERVAL_MS = Math.max(
  Number(process.env.REACT_APP_CHART_REDRAW_INTERVAL_MS) || 250,
  50
);
// Minimum horizontal pixels reserved per x-axis tick label so timestamps have
// room to render without overlapping when the chart is narrow or many samples
// have arrived (which pushes more ticks into the same visible window).
const MIN_PX_PER_X_TICK = 65;
// Minimum vertical pixels reserved per y-axis tick label for the same reason.
const MIN_PX_PER_Y_TICK = 32;

// Formats Y-axis and tooltip values with fixed decimals or scientific notation.
const formatChartValue = (value) => {
  const abs = Math.abs(value);
  if (!Number.isFinite(value)) return "—";
  if (abs === 0) return "0";
  return abs >= 0.01 ? value.toFixed(3) : value.toExponential(2);
};

// Computes how many axis ticks fit in the given pixel span without crowding.
// This shrinks automatically as the chart gets narrower/shorter instead of
// always drawing a fixed count of ticks regardless of available space.
const getAdaptiveTickCount = (pixelSpan, minPxPerTick) =>
  Math.max(2, Math.floor(pixelSpan / minPxPerTick));

// Picks a time format whose precision matches how zoomed-in the visible
// x-domain currently is. A fixed "HH:MM:SS.mmm" format becomes unreadable
// once samples arrive fast enough that the visible window only spans a
// couple of seconds — every tick repeats the same hour/minute digits, which
// wastes the space needed to show the digits that are actually changing.
const getAdaptiveTimeFormatter = (domainSpanMs) => {
  if (domainSpanMs < 2000) {
    // Sub-2s window: hours/minutes never change here, show seconds.milliseconds only.
    return (xValue) => d3.timeFormat("%S.%L")(new Date(Math.floor(xValue)));
  }
  if (domainSpanMs < 60 * 1000) {
    return (xValue) => d3.timeFormat("%M:%S.%L")(new Date(Math.floor(xValue)));
  }
  if (domainSpanMs < 60 * 60 * 1000) {
    return (xValue) => d3.timeFormat("%H:%M:%S")(new Date(Math.floor(xValue)));
  }
  if (domainSpanMs < 24 * 60 * 60 * 1000) {
    return (xValue) => d3.timeFormat("%H:%M")(new Date(Math.floor(xValue)));
  }
  return (xValue) => d3.timeFormat("%b %d %H:%M")(new Date(Math.floor(xValue)));
};

// Walks rendered axis tick labels in order and hides any label that would
// overlap the last visible one. This is a safety net for cases the tick-count
// estimate above doesn't fully cover (unexpected font metrics, very long
// formatted values, etc.), so labels never visually collide.
const hideOverlappingTickLabels = (axisGroup, isHorizontalAxis) => {
  // Tracks the far edge (right for x-axis, bottom for y-axis) of the last label kept visible.
  let lastVisibleEdge = -Infinity;
  axisGroup.selectAll(".tick").each(function hideIfOverlapping() {
    const tickText = d3.select(this).select("text");
    if (tickText.empty()) return;
    const bbox = tickText.node().getBBox();
    const transform = d3.select(this).attr("transform") || "";
    const translateMatch = /translate\(([-\d.]+)[ ,]([-\d.]+)/.exec(transform);
    const tickPosition = translateMatch
      ? Number(translateMatch[isHorizontalAxis ? 1 : 2])
      : 0;
    const start = tickPosition + (isHorizontalAxis ? bbox.x : bbox.y);
    const end = start + (isHorizontalAxis ? bbox.width : bbox.height);
    // 6px gap keeps adjacent labels visually separated, not just barely non-overlapping.
    if (start < lastVisibleEdge + 6) {
      tickText.style("display", "none");
    } else {
      tickText.style("display", null);
      lastVisibleEdge = end;
    }
  });
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

  // `onlyDataset` lets the frequent redraw path skip building/sorting the series this
  // particular chart instance never renders — each LineChart only ever plots one of
  // force/displacement, so computing both on every redraw wastes CPU on slower hardware
  // (e.g. a Raspberry Pi) once the buffer holds thousands of high-rate samples.
  // Defaults to computing both so the ref API (used by CSV/legacy consumers) is unchanged.
  const transformData = (dataBuffer, onlyDataset = null) => {
    const series1 = [];
    const series2 = [];
    const needsDisplacement = onlyDataset !== "force";
    const needsForce = onlyDataset == null || onlyDataset === "force";
    const { points, xValues } = resolvePlotXValues(dataBuffer);
    const latestPoint = points[points.length - 1];
    const shouldDeferLatestGroup =
      latestPoint && !latestPoint.hasHighResolutionTimestamp;

    dataBuffer.forEach((item, index) => {
      const timestamp =
        item.timestamp_ms ?? item.timestamp ?? item.time ?? item.t;
      const xValue = xValues[index];
      const displacement =
        !needsDisplacement || item.displacement == null
          ? NaN
          : Number(item.displacement);
      const force =
        !needsForce || item.force == null ? NaN : Number(item.force);

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

  // Reduces a chronologically-sorted series to roughly one min/max value-pair per
  // horizontal pixel column. Drawing more than that is wasted work — the extra points
  // land on the same pixel and are visually indistinguishable — but it's exactly what
  // happens once samples arrive in the hundreds/thousands per second, so this is the
  // single biggest lever for keeping the chart smooth on constrained hardware.
  const downsampleForRender = (sortedSeries, chartWidth, xDomain) => {
    const pointCount = sortedSeries.length;
    const bucketCount = Math.max(1, Math.floor(chartWidth));
    // Already at or below the target resolution — downsampling would only cost extra work.
    if (pointCount <= bucketCount * 2) return sortedSeries;

    const [xStart, xEnd] = xDomain;
    const xSpan = xEnd - xStart || 1;
    const downsampled = [];
    let bucketStartIndex = 0;

    for (let bucket = 0; bucket < bucketCount; bucket += 1) {
      const bucketEndX = xStart + ((bucket + 1) / bucketCount) * xSpan;
      let bucketEndIndex = bucketStartIndex;
      while (
        bucketEndIndex < pointCount &&
        sortedSeries[bucketEndIndex].xValue <= bucketEndX
      ) {
        bucketEndIndex += 1;
      }

      if (bucketEndIndex > bucketStartIndex) {
        let minPoint = sortedSeries[bucketStartIndex];
        let maxPoint = sortedSeries[bucketStartIndex];
        for (let i = bucketStartIndex + 1; i < bucketEndIndex; i += 1) {
          const point = sortedSeries[i];
          if (point.value < minPoint.value) minPoint = point;
          if (point.value > maxPoint.value) maxPoint = point;
        }

        if (minPoint === maxPoint) {
          downsampled.push(minPoint);
        } else if (minPoint.xValue <= maxPoint.xValue) {
          // Keep chronological order within the bucket so the line doesn't zig-zag backwards.
          downsampled.push(minPoint, maxPoint);
        } else {
          downsampled.push(maxPoint, minPoint);
        }
        bucketStartIndex = bucketEndIndex;
      }
    }

    // Any leftover points past the last full bucket (rounding) are kept as-is.
    for (let i = bucketStartIndex; i < pointCount; i += 1) {
      downsampled.push(sortedSeries[i]);
    }

    return downsampled;
  };

  const downloadDataBufferAsCSV = () => {
    if (!dataBuffer || dataBuffer.length === 0) {
      alert("No data available to download.");
      return;
    }

    const csvContent = [["Timestamp", `Z (${DISPLACEMENT_UNIT})`, `Force (${FORCE_UNIT_LABEL})`]];
    dataBuffer.forEach((item) => {
      const displacement = item.displacement == null ? "" : Number(item.displacement);
      const force = item.force == null ? "" : Number(item.force);
      csvContent.push([
        item.timestamp_ms ?? item.timestamp ?? "",
        Number.isFinite(displacement) ? displacement : "",
        Number.isFinite(force) ? force : "",
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

      const data = transformData(activeDataBuffer, activeDataset);
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

      // Down to ~1-2 rendered points per pixel column — see downsampleForRender above.
      // The full-resolution `series` is kept around for accurate tooltip lookups and for
      // re-slicing/re-downsampling whenever the brush below zooms into a narrower window.
      const renderSeries = downsampleForRender(series, chartWidth, xDomain);

      linesGroup
        .append("path")
        .datum(renderSeries)
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

      // Renders visible dot markers for a (already downsampled) set of points using D3's
      // enter/update/exit join, so re-invoking this after a brush/zoom just patches the
      // existing circles instead of tearing them all down and reattaching listeners.
      // Markers carry no listeners of their own — see the shared pointer overlay below —
      // which matters once thousands of samples/sec would otherwise mean thousands of
      // per-circle mouse handlers.
      const MAX_RENDERED_MARKERS = 600;
      function renderPointMarkers(pointsToRender) {
        const visiblePoints =
          pointsToRender.length <= MAX_RENDERED_MARKERS ? pointsToRender : [];
        return linesGroup
          .selectAll(`.point-${activeDataset}`)
          .data(visiblePoints)
          .join("circle")
          .attr("class", `point-${activeDataset}`)
          .attr("cx", (d) => x(d.xValue))
          .attr("cy", (d) => y(d.value))
          .attr("r", 4)
          .attr("fill", activeDataset === "force" ? "#FF9800" : "#009688");
      }

      renderPointMarkers(renderSeries);

      // Finds the closest real (full-resolution) sample to a pointer x-position via binary
      // search, so hovering anywhere over the chart shows an accurate tooltip in O(log n)
      // regardless of how many raw points are buffered — a single listener here replaces
      // what used to be one mouseover/mousemove/mouseout triple per rendered point.
      const bisectXValue = d3.bisector((d) => d.xValue).left;
      // `currentSeries`/`currentX` are updated by `brushed()` below so this overlay keeps
      // resolving against whatever data/scale is currently zoomed in, without re-registering listeners.
      let currentSeries = series;
      let currentX = x;

      function findNearestPoint(targetXValue) {
        const insertionIndex = bisectXValue(currentSeries, targetXValue);
        const candidateBefore = currentSeries[insertionIndex - 1];
        const candidateAfter = currentSeries[insertionIndex];
        if (!candidateBefore) return candidateAfter;
        if (!candidateAfter) return candidateBefore;
        return Math.abs(candidateBefore.xValue - targetXValue) <=
          Math.abs(candidateAfter.xValue - targetXValue)
          ? candidateBefore
          : candidateAfter;
      }

      chartGroup
        .append("rect")
        .attr("class", "pointer-overlay")
        .attr("width", chartWidth)
        .attr("height", chartHeight)
        .attr("fill", "transparent")
        .style("cursor", "crosshair")
        .on("mousemove", (event) => {
          const [pointerX] = d3.pointer(event);
          const nearestPoint = findNearestPoint(currentX.invert(pointerX));
          if (!nearestPoint) return;
          showTooltip(event, nearestPoint, activeDataset === "force" ? "Force" : "Z");
          moveTooltip(event);
        })
        .on("mouseout", hideTooltip);

      // Tick count/format both scale with the current view instead of a fixed "10 ticks,
      // full HH:MM:SS.mmm" layout, so labels stay legible whether the visible window
      // spans hours or a fast-arriving burst of samples a few seconds wide.
      const xTickCount = getAdaptiveTickCount(chartWidth, MIN_PX_PER_X_TICK);
      const xTickFormatter = getAdaptiveTimeFormatter(xDomain[1] - xDomain[0]);

      const xAxisGroup = chartGroup
        .append("g")
        .attr("class", "x-axis")
        .attr("transform", `translate(0,${chartHeight})`)
        .call(d3.axisBottom(x).ticks(xTickCount).tickFormat(xTickFormatter));

      xAxisGroup.selectAll(".tick text").attr("fill", axisTextColor);
      xAxisGroup.selectAll(".tick line, .domain").attr("stroke", axisLineColor);
      hideOverlappingTickLabels(xAxisGroup, true);

      xAxisGroup
        .append("text")
        .attr("class", "x-axis-label")
        .attr("x", chartWidth / 2)
        .attr("y", 35)
        .attr("fill", axisTextColor)
        .attr("text-anchor", "middle")
        .text("Time");

      // Y-axis tick count also scales with the available height for the same reason.
      const yTickCount = getAdaptiveTickCount(chartHeight, MIN_PX_PER_Y_TICK);
      const yAxisGroup = chartGroup
        .append("g")
        .attr("class", "y-axis")
        .call(
          d3
            .axisLeft(y)
            .ticks(yTickCount)
            .tickFormat((d) => formatChartValue(d))
        );

      yAxisGroup.selectAll(".tick text").attr("fill", axisTextColor);
      yAxisGroup.selectAll(".tick line, .domain").attr("stroke", axisLineColor);
      hideOverlappingTickLabels(yAxisGroup, false);

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
        .datum(renderSeries)
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

          // Re-downsample from the full-resolution series for just the zoomed-in window —
          // reusing the original whole-buffer downsample here would hide the extra detail
          // zooming in is supposed to reveal.
          const zoomedRenderSeries = filteredSeries.length
            ? downsampleForRender(filteredSeries, chartWidth, [x0, x1])
            : [];

          linesGroup
            .select(`.line-${activeDataset}`)
            .datum(zoomedRenderSeries)
            .attr("d", line);

          renderPointMarkers(zoomedRenderSeries);

          // Keeps the shared pointer-overlay tooltip resolving against the zoomed window.
          currentSeries = filteredSeries.length ? filteredSeries : series;
          currentX = x;

          // Re-derive tick count/format for the zoomed-in domain so a brushed
          // selection spanning only a second or two still gets readable, non-repetitive labels.
          const zoomedXTickCount = getAdaptiveTickCount(chartWidth, MIN_PX_PER_X_TICK);
          const zoomedXTickFormatter = getAdaptiveTimeFormatter(x1 - x0);
          xAxisGroup.call(
            d3.axisBottom(x).ticks(zoomedXTickCount).tickFormat(zoomedXTickFormatter)
          );
          xAxisGroup.selectAll(".tick text").attr("fill", axisTextColor);
          xAxisGroup.selectAll(".tick line, .domain").attr("stroke", axisLineColor);
          hideOverlappingTickLabels(xAxisGroup, true);

          const zoomedYTickCount = getAdaptiveTickCount(chartHeight, MIN_PX_PER_Y_TICK);
          yAxisGroup.call(
            d3
              .axisLeft(y)
              .ticks(zoomedYTickCount)
              .tickFormat((d) => formatChartValue(d))
          );
          yAxisGroup.selectAll(".tick text").attr("fill", axisTextColor);
          yAxisGroup.selectAll(".tick line, .domain").attr("stroke", axisLineColor);
          hideOverlappingTickLabels(yAxisGroup, false);

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
