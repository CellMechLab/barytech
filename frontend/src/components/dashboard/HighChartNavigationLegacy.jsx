import React, { useContext } from "react";
import Highcharts from "highcharts";
import HighchartsReact from "highcharts-react-official";
import HighchartsStock from "highcharts/modules/stock";
import { useTheme } from "@mui/material";
import { tokens } from "../../theme";
import { WebSocketContext } from "./WebSocketProvider";
// Initialize Highcharts Stock
HighchartsStock(Highcharts);

const TimeSlider = ({ chartData, onTimeRangeChange }) => {
  const { dataBuffer1 } = useContext(WebSocketContext);
  // const transformDataForTimeSlider = (dataBuffer) => {
  //   return [
  //     {
  //       name: "Data1",
  //       data: dataBuffer.map((item) => ({
  //         x: new Date(item.timestamp).getTime(),  // Timestamp as x
  //         y: item.data1,                         // Data1 as y
  //       })),
  //     },
  //     {
  //       name: "Data2",
  //       data: dataBuffer.map((item) => ({
  //         x: new Date(item.timestamp).getTime(),  // Timestamp as x
  //         y: item.data2,                         // Data2 as y
  //       })),
  //     },
  //   ];
  // };
  const transformDataForTimeSlider = (dataBuffer) => {
    return dataBuffer.map((item) => ({
      x: new Date(item.timestamp).getTime(), // Timestamp as x
      y: item.data1, // Data1 as y
    }));
  };
  // Transform data to match Highcharts format
  const data = transformDataForTimeSlider(dataBuffer1);
  // let data = [
  //   { x: 1668931199000, y: 512 },
  //   { x: 1668931299000, y: 243 },
  //   { x: 1668931399000, y: 870 },
  // ];
    console.log(data);

  const theme = useTheme();
  const colors = tokens(theme.palette.mode);
  const options = {
    chart: {
      type: "line", // Main chart type
      height: 100, // Set the desired height in pixels (e.g., 500)
      backgroundColor: colors.primary[400],
    },
    title: {
      // text: "Main Chart with Navigator",
    },
    xAxis: {
      type: "datetime", // For time-based data
    },
    series: [
      {
        name: "Main Data Series",
        data: data,
      },
    ],
    navigator: {
      enabled: true,
      series: {
        type: "areaspline", // Type for the navigator chart
        data: data,
      },
    },
    rangeSelector: {
      enabled: true, // Optional range selector for date ranges
      buttons: [
        {
          type: "hour",
          count: 1,
          text: "1h",
        },
        {
          type: "hour",
          count: 6,
          text: "6h",
        },
        {
          type: "day",
          count: 1,
          text: "1d",
        },
        {
          type: "all",
          text: "All",
        },
      ],
      selected: 1,
    },
    scrollbar: {
      enabled: true, // Scrollbar linked to the navigator
    },
    events: {
      // Event handler to capture range selection change
      afterSetExtremes: function (e) {
        if (onTimeRangeChange) {
          const newMin = e.min; // New minimum timestamp
          const newMax = e.max; // New maximum timestamp
          onTimeRangeChange([newMin, newMax]);
        }
      },
    },
  };

  return (
    <HighchartsReact
      highcharts={Highcharts}
      constructorType={"stockChart"}
      options={options}
    />
  );
};

export default TimeSlider;
