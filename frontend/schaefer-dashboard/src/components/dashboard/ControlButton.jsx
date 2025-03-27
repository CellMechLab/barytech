import React, { useContext } from "react";
import { IconButton } from "@mui/material";
import { WebSocketContext } from "./WebSocketProvider";
import PowerSettingsNewIcon from "@mui/icons-material/PowerSettingsNew";
import SaveAlt from "@mui/icons-material/SaveAlt";
import { useTheme } from "@mui/material";
import { tokens } from "../../theme";
import { useSave } from "../../context/SaveContext";
import { toast } from "sonner"; // Import Sonner's toast function

const Controls = ({ type }) => {
  const theme = useTheme();
  const colors = tokens(theme.palette.mode);
  const { saveEnabled, setSaveEnabled } = useSave();

  const { toggleConnection, connected, socket } = useContext(WebSocketContext);

  const handleButtonClick = () => {
    if (type === "connection") {
      toggleConnection();
      toast(
        connected
          ? "WebSocket connection closed."
          : "WebSocket connection initiated.",
        {
          style: {
            backgroundColor: connected ? "#3da58a" : "#9ccbb3",
            color: "white",
          },
        }
      );
    } else if (type === "save") {
      if (socket && socket.readyState === WebSocket.OPEN) {
        const newSaveState = !saveEnabled;
        setSaveEnabled(newSaveState);

        // Data to send over WebSocket
        const data = { type: "save", save: newSaveState };
        socket.send(JSON.stringify(data));

        // Show toast message
        toast(
          newSaveState
            ? "Save mode enabled! Data will now be saved."
            : "Save mode disabled! Data saving stopped.",
          {
            style: {
              backgroundColor: newSaveState ? "#3da58a" : "#d32f2f",
              color: "white",
            },
          }
        );
      } else {
        // Show alert and toast message if WebSocket is not open
        toast.error("WebSocket connection is not established!", {
          style: {
            backgroundColor: "red",
            color: "white",
          },
        });
        console.log("WebSocket is not open. Cannot send data.");
      }
    }
  };

  const isConnectionButton = type === "connection";
  const buttonStyles = {
    width: "80px", // Default width
    height: "80px", // Default height
    borderRadius: "15%",
    backgroundColor: isConnectionButton
    ? connected
      ? "#3da58a" // Connected true
      : "#9ccbb3" // Connected false
    : saveEnabled
      ? "#3da58a" // SaveEnabled true
      : "#9ccbb3", // SaveEnabled false
  
  "&:hover": {
    backgroundColor: isConnectionButton
      ? connected
        ? "#358c73" // Hover: Connected true
        : "#388e3c" // Hover: Connected false
      : saveEnabled
        ? "#358c73" // Hover: SaveEnabled true
        : "#388e3c", // Hover: SaveEnabled false
  },
  "@media (max-width: 800px)": {
    width: "300px",
    height: "100px",
  },
  }  

  return (
    <div className="controls">
      <IconButton
        aria-label={
          isConnectionButton
            ? connected
              ? "Turn Off"
              : "Turn On"
            : "Save Data"
        }
        color={isConnectionButton ? (connected ? "error" : "success") : "primary"}
        onClick={handleButtonClick}
        sx={buttonStyles}
      >
        {isConnectionButton ? (
          <PowerSettingsNewIcon sx={{ fontSize: 50, color: "white" }} />
        ) : (
          <SaveAlt sx={{ fontSize: 50, color: "white" }} />
        )}
      </IconButton>
    </div>
  );
};

export default Controls;
