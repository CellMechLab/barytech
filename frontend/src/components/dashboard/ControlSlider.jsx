import React, { useContext, useState } from "react";
import { WebSocketContext } from "./WebSocketProvider";
import "../../index.css"; // Import CSS file for styling
import { Typography, Box, Slider, useTheme, useMediaQuery } from "@mui/material";
import { styled } from "@mui/material/styles";
import { tokens } from "../../theme";

const Separator = styled("div")(
  ({ theme }) => `
  height: ${theme.spacing(2)}; // Reduced spacing between sliders
`
);

const Controls = () => {
  const { socket } = useContext(WebSocketContext);
  const [force, setForce] = useState(50);
  const [displacement, setDisplacement] = useState(20);

  const forceMarks = [
    { value: 0, label: "0 N" },
    { value: 25, label: "25 N" },
    { value: 50, label: "50 N" },
    { value: 75, label: "75 N" },
    { value: 100, label: "100 N" },
  ];

  const displacementMarks = [
    { value: 0, label: "0 mm" },
    { value: 35, label: "35 mm" },
    { value: 70, label: "70 mm" },
    { value: 100, label: "100 mm" },
  ];

  const handleForceChange = (event, value) => {
    setForce(value);

    if (socket && socket.readyState === WebSocket.OPEN) {
      console.log("WebSocket open, sending force data...");
      socket.send(
        JSON.stringify({
          type: "slider",
          parameter: "force",
          value,
        })
      );
    } else {
      alert("WebSocket is not open. Cannot send data."); // Show alert
      console.log("WebSocket is not open. Cannot send data.");
    }
  };

  const handleDisplacementChange = (event, value) => {
    setDisplacement(value);

    if (socket && socket.readyState === WebSocket.OPEN) {
      console.log("WebSocket open, sending displacement data...");
      socket.send(
        JSON.stringify({
          type: "slider",
          parameter: "displacement",
          value,
        })
      );
    } else {
      alert("WebSocket is not open. Cannot send data."); // Show alert
      console.log("WebSocket is not open. Cannot send data.");
    }
  };

  const valuetext = (value) => `${value}`;

  const theme = useTheme();
  const colors = tokens(theme.palette.mode);
  const isSmallScreen = useMediaQuery(theme.breakpoints.down("sm"));

  return (
    <Box
      sx={{
        width: "95%", // Use 100% width for small screens
        paddingTop: "5px", // Reduce padding for small screens
        paddingLeft: "14px",
        paddingRight: "20px",
        paddingBottom: "5px",
        overflow: "hidden", // Prevent overflow
      }}
    >
      {/* Force Slider */}
      <Typography
        variant={isSmallScreen ? "h6" : "h5"} // Adjust font size for responsiveness
        color={colors.greenAccent[500]}
        sx={{ mt: "10px", mb: "0px" }} // Reduced top and bottom margins
        gutterBottom
      >
        Force
      </Typography>
      <Slider
        track={false}
        getAriaValueText={valuetext}
        value={force}
        onChange={handleForceChange}
        marks={forceMarks}
        min={0}
        max={100}
        sx={{
          mt: "5px", // Reduced margin above the slider
          mb: "5px", // Reduced margin below the slider
          width: "100%", // Ensure slider fits fully in the container
          mx: "auto", // Center the slider
        }}
      />
      <Separator />

      {/* Displacement Slider */}
      <Typography
        variant={isSmallScreen ? "h6" : "h5"} // Adjust font size for responsiveness
        color={colors.greenAccent[500]}
        sx={{ mt: "10px", }} // Reduced top and bottom margins
        gutterBottom
      >
        Displacement
      </Typography>
      <Slider
        track={false}
        getAriaValueText={valuetext}
        value={displacement}
        onChange={handleDisplacementChange}
        marks={displacementMarks}
        min={0}
        max={100}
        sx={{
          mt: "5px", // Reduced margin above the slider
          mb: "5px", // Reduced margin below the slider
          width: "100%", // Ensure slider fits fully in the container
          mx: "auto", // Center the slider
        }}
      />
    </Box>
  );
};

export default Controls;
