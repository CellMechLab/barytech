import React, { useEffect, useRef } from "react";
import * as d3 from "d3";

const LineChartWithArea = ({ lineColor, areaColor, data }) => {
  const svgRef = useRef();

  useEffect(() => {
    if (!Array.isArray(data)) {
      console.error("Data must be an array:", data);
      return;
    }

    if (
      data.some((d) => !(d.date instanceof Date) || typeof d.value !== "number")
    ) {
      console.error(
        "Each data point must have a valid `date` and `value`:",
        data
      );
      return;
    }
    console.log(data);
    const resizeChart = () => {
      console.log("resize");
      const container = svgRef.current.parentNode; // Get parent container
      const width = container.offsetWidth;
      const height = container.offsetHeight * 0.4; // 30% of parent's height

      const margin = { top: 0, right: 0, bottom: 0, left: 0 };

      const svg = d3.select(svgRef.current);
      svg.selectAll("*").remove(); // Clear previous drawings

      const xScale = d3
        .scaleTime()
        .domain(d3.extent(data, (d) => d.date)) // Ensure `d.date` is a Date object
        .range([margin.left, width - margin.right]);

      const yScale = d3
        .scaleLinear()
        .domain([0, d3.max(data, (d) => d.value)]) // Ensure `d.value` is a valid number
        .range([height - margin.bottom, margin.top]);

      // Define a gradient for the area
      const defs = svg.append("defs");

      const gradient = defs
        .append("linearGradient")
        .attr("id", "area-gradient")
        .attr("x1", "0%")
        .attr("y1", "0%")
        .attr("x2", "0%")
        .attr("y2", "100%"); // Vertical gradient

      gradient
        .append("stop")
        .attr("offset", "0%")
        .attr("stop-color", areaColor)
        .attr("stop-opacity", 0.6);

      gradient
        .append("stop")
        .attr("offset", "100%")
        .attr("stop-color", areaColor)
        .attr("stop-opacity", 0.1); // Lighter and more transparent at the bottom

      // Area generator
      const area = d3
        .area()
        .x((d) => xScale(d.date))
        .y0(height) // Ensure the area starts at the bottom of the SVG
        .y1((d) => yScale(d.value)); // Top of the area

      // Line generator
      const line = d3
        .line()
        .x((d) => xScale(d.date))
        .y((d) => yScale(d.value));

      // Set SVG dimensions
      svg.attr("width", width).attr("height", height);

      // Append area with gradient fill
      svg
        .append("path")
        .datum(data)
        .attr("d", area)
        .attr("fill", "url(#area-gradient)"); // Use the gradient defined above

      // Append line
      svg
        .append("path")
        .datum(data)
        .attr("d", line)
        .attr("fill", "none")
        .attr("stroke", lineColor)
        .attr("stroke-width", 2);
    };

    // Initial render
    resizeChart();

    // Add event listener for window resize
    window.addEventListener("resize", resizeChart);

    return () => {
      // Cleanup event listener
      window.removeEventListener("resize", resizeChart);
    };
  }, [lineColor, areaColor, data]);

  return <svg ref={svgRef} style={{ width: "100%", height: "100%" }} />;
};

export default LineChartWithArea;
