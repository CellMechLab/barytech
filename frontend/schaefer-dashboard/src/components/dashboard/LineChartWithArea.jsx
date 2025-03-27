import React, { useEffect, useRef } from "react";
import * as d3 from "d3";

const LineChartWithArea = ({ lineColor, areaColor, data }) => {
  const svgRef = useRef();
  // console.log(areaColor, lineColor)
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
    const container = svgRef.current.parentNode;
    const tooltip = d3
    .select(container)
    .append("div")
    .style("position", "absolute")
    .style("background", "white")
    .style("border", "1px solid black")
    .style("padding", "5px")
    .style("border-radius", "5px")
    .style("pointer-events", "none")
    .style("z-index", "100000")
    .style("opacity", 0); // Initially hidden
    const resizeChart = () => {
      
      const width = container.offsetWidth;
      const height = container.offsetHeight;

      const margin = { top: 0, right: 0, bottom: 0, left: 0 };

      const svg = d3.select(svgRef.current);
      svg.selectAll("*").remove(); // Clear previous drawings

      const xScale = d3
        .scaleTime()
        .domain(d3.extent(data, (d) => d.date))
        .range([margin.left, width - margin.right]);

      const yScale = d3
        .scaleLinear()
        .domain([0, d3.max(data, (d) => d.value)])
        .range([height - margin.bottom, margin.top]);

      const area = d3
        .area()
        .x((d) => xScale(d.date))
        .y0(height)
        .y1((d) => yScale(d.value));

      const line = d3
        .line()
        .x((d) => xScale(d.date))
        .y((d) => yScale(d.value));

      svg.attr("width", width).attr("height", height);

      // Append area
      svg
        .append("path")
        .datum(data)
        .attr("d", area)
        .attr("fill", areaColor);

      // Append line
      svg
        .append("path")
        .datum(data)
        .attr("d", line)
        .attr("fill", "none")
        .attr("stroke", lineColor)
        .attr("stroke-width", 2);

      // Create a vertical line
      const verticalLine = svg
        .append("line")
        .attr("stroke", "#aaa")
        .attr("stroke-width", 1)
        .attr("y1", margin.top)
        .attr("y2", height - margin.bottom)
        .style("opacity", 0); // Hidden by default

      // Add overlay for hover detection
      const overlay = svg
        .append("rect")
        .attr("width", width)
        .attr("height", height)
        .attr("fill", "none")
        .attr("pointer-events", "all");


        
      // Mouse move handler
      const handleMouseMove = (event) => {
        const [mouseX] = d3.pointer(event);
      
        // Find the closest data point
        const bisector = d3.bisector((d) => d.date).left;
        const xDate = xScale.invert(mouseX);
        const index = bisector(data, xDate, 1);
      
        // Ensure the index is within bounds
        const a = data[index - 1];
        const b = data[index];
      
        // Check if 'a' and 'b' are valid
        let closestPoint;
        if (a && b) {
          closestPoint = xDate - a.date > b.date - xDate ? b : a;
        } else {
          closestPoint = a || b; // Use the only defined point
        }
      
        if (!closestPoint) {
          // No valid point, return early
          return;
        }
      
        // Update vertical line position
        verticalLine
          .attr("x1", xScale(closestPoint.date))
          .attr("x2", xScale(closestPoint.date))
          .attr("stroke-width", 2)
          .attr("stroke", "black") // Correctly apply stroke color
          .style("opacity", 1);
      
        // Update tooltip content and position
        tooltip
          .html(
            `<strong>Date:</strong> ${closestPoint.date.toLocaleDateString()}<br/>
             <strong>Value:</strong> ${closestPoint.value}`
          )
          .style("left", `${d3.pointer(event, container)[0] + 10}px`)
          .style("top", `${d3.pointer(event, container)[1] - 10}px`)
          .style("opacity", 1); // Show tooltip
      };
      
          
     
      // Mouse leave handler
      const handleMouseLeave = () => {
        verticalLine.style("opacity", 0); // Hide the vertical line
        tooltip.style("opacity", 0); // Hide the tooltip

      };

      // Add event listeners
      overlay
        .on("mousemove", handleMouseMove)
        .on("mouseleave", handleMouseLeave);
    };

    resizeChart();

    window.addEventListener("resize", resizeChart);
    return () => {
      window.removeEventListener("resize", resizeChart);
      tooltip.remove(); // Remove tooltip div
    };
  }, [lineColor, areaColor, data]);

  return <svg ref={svgRef} style={{ width: "100%", height: "100%", borderBottomLeftRadius: "10px", borderBottomRightRadius: "10px" }} />;
};

export default LineChartWithArea;
