// Dashboard page for live monitoring, charting, and printer controls.
import {
  Box,
  Button,
  IconButton,
  Typography,
  useTheme,
  useMediaQuery,
} from "@mui/material";
import { tokens } from "../../theme";
import DownloadOutlinedIcon from "@mui/icons-material/DownloadOutlined";
import Header from "./Header";
import LineChart from "./LineChart";
import StatBox from "./StatBox";
import ControlButton from "./ControlButton";
import { useState, useCallback, useRef, useContext, useEffect } from "react";
import DraggableBox from "./DraggableBox"; // Import DraggableBox component
import { WebSocketContext } from "./WebSocketProvider";
import usePrinterControls from "./hooks/usePrinterControls";
import useDeviceDataExport from "./hooks/useDeviceDataExport";
import BoltIcon from "@mui/icons-material/Bolt";
import SwapHorizIcon from "@mui/icons-material/SwapHoriz";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import ThermostatIcon from "@mui/icons-material/Thermostat";
import MyLocationIcon from "@mui/icons-material/MyLocation";
import HomeIcon from "@mui/icons-material/Home";
import StopIcon from "@mui/icons-material/Stop";
import LinkIcon from "@mui/icons-material/Link";
import LinkOffIcon from "@mui/icons-material/LinkOff";
import FileDownloadIcon from "@mui/icons-material/FileDownload";
import FileUploadIcon from "@mui/icons-material/FileUpload";
import { VIDEO_BASE_URL } from "../../config/endpoints";

const Dashboard = () => {
  // Stores backend base URL used for printer and export API calls.
  const backendApiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const theme = useTheme();
  const colors = tokens(theme.palette.mode);
  const [totalDataPoints, setTotalDataPoints] = useState(0);
  const { dataBuffer } = useContext(WebSocketContext);
  const [saveEnabled, setSaveEnabled] = useState(false);

  // Printer state and command handlers — all fetch/WS logic lives in the hook.
  const {
    printerActionInProgress,
    printerActionStatus,
    printerPosition,
    bedTemperature,
    hotendTemperature,
    jogStep,
    setJogStep,
    printerConnected,
    handleJogAxis,
    handleHomePrinter,
    handleEmergencyStop,
    handleExtrude,
    handleRetract,
    handleConnectPrinter,
    handleDisconnectPrinter,
  } = usePrinterControls(backendApiUrl);

  // Export handler — fetch/download logic lives in the hook.
  const { downloadDeviceData } = useDeviceDataExport(backendApiUrl);

  const handleDataPointCountChange = (count) => {
    setTotalDataPoints(count);
  };
  const isSmallScreen = useMediaQuery("(max-width:800px)");
  const isMediumScreen = useMediaQuery(
    "(min-width:800px) and (max-width:1024px)"
  );
  const isLargeScreen = useMediaQuery(
    "(min-width:1025px) and (max-width:1440px)"
  );
  // Detects compact 7-inch landscape displays so the dashboard can use tighter spacing.
  const isSevenInchDisplay = useMediaQuery(
    "(max-width:1024px) and (max-height:700px)"
  );
  // Dynamically adjust font sizes for title
  const titleFontSize = isSmallScreen
    ? "14px"
    : isSevenInchDisplay
    ? "15px"
    : isMediumScreen
    ? "16px"
    : isLargeScreen
    ? "18px"
    : "20px";

  const subtitleFontSize = isSmallScreen
    ? "15px"
    : isSevenInchDisplay
    ? "14px"
    : isMediumScreen
    ? "16px"
    : isLargeScreen
    ? "15px"
    : "22px";
  // Hides the dashboard header on compact panels to preserve vertical room for controls.
  const showDashboardHeader = !isSmallScreen && !isSevenInchDisplay;
  // Shrinks outer padding on compact panels so cards use more of the screen.
  const dashboardOuterMargin = isSevenInchDisplay ? "10px" : "20px";
  // Reduces the grid gap on compact panels to fit more content above the fold.
  const dashboardGridGap = isSevenInchDisplay ? "12px" : "20px";
  // Lowers row height on compact panels so large cards do not extend too far vertically.
  const dashboardGridAutoRows = isSevenInchDisplay ? "118px" : "140px";
  const [transformedData, setTransformedData] = useState({
    series1: [],
    series2: [],
  });
  const [series1Data, setSeries1Data] = useState([]);
  const [series2Data, setSeries2Data] = useState([]);


  useEffect(() => {
    // console.log("dataBuffer1");
    if (chartRef.current) {
      const data = chartRef.current.transformData(dataBuffer);
      // console.log("transformeddata", data);
      setTransformedData(data);
    }
  }, [dataBuffer]);

  useEffect(() => {
    setSeries1Data(transformedData.series1 || []);
    setSeries2Data(transformedData.series2 || []);
  }, [transformedData]);

  useEffect(() => {
    setBoxes((prevBoxes) =>
      prevBoxes.map((box) => {
        if (box.id === 3) {
          return { ...box, data: transformedData.series1 };
        } else if (box.id === 4) {
          return { ...box, data: transformedData.series2 };
        }
        return box;
      })
    );
  }, [transformedData]);

  const chartRef = useRef();
  const handleDownload = () => {
    if (chartRef.current) {
      chartRef.current.downloadChart(); // Call the downloadChart method
    }
  };

  const setChartRef = useCallback((ref) => {
    chartRef.current = ref;
  }, []);
  const handleDrop = (fromId, toId) => {
    const newBoxes = [...boxes];
    const fromBox = newBoxes.find((box) => box.id === fromId);
    const toBox = newBoxes.find((box) => box.id === toId);

    if (!fromBox || !toBox) return;

    // Swap gridColumn and gridRow between fromBox and toBox
    [fromBox.gridColumn, toBox.gridColumn] = [
      toBox.gridColumn,
      fromBox.gridColumn,
    ];
    [fromBox.gridRow, toBox.gridRow] = [toBox.gridRow, fromBox.gridRow];

    setBoxes(newBoxes);
  };
  const handleHover = (fromId, toId) => {
    // Create a copy of the boxes array
    const newBoxes = [...boxes];

    // Find the indices of the dragged and target items
    const fromIndex = newBoxes.findIndex((box) => box.id === fromId);
    const toIndex = newBoxes.findIndex((box) => box.id === toId);

    if (fromIndex === -1 || toIndex === -1) return;

    // Swap the positions in the array without changing box sizes
    [newBoxes[fromIndex], newBoxes[toIndex]] = [
      newBoxes[toIndex],
      newBoxes[fromIndex],
    ];

    // Update state with the reordered boxes
    setBoxes(newBoxes);
  };

  const handleDelete = (id) => {
    console.log(boxes[id]);
    setBoxes((prevBoxes) => prevBoxes.filter((box) => box.id !== id));
  };

  const [boxes, setBoxes] = useState([
    {
      id: 9,
      // Uses extra width on desktop because this card now includes controls + status.
      gridColumn: "span 8",
      // Reduced to span 2 (~75% of previous span 3 height) to keep the card compact.
      gridRow: "span 2",
      // Content is overridden every render in updatedBoxes to keep state fresh.
      content: null,
    },
    {
      id: 10,
      gridColumn: "span 4",
      // Keeps first-row box heights consistent with other first-row cards.
      gridRow: "span 2",
      // Content is overridden every render in updatedBoxes to keep state fresh.
      content: null,
    },
    {
      id: 7,
      gridColumn: "span 12",
      gridRow: "span 3",
      content: (
        <Box width="100%">
          <Box
            mt="25px"
            p="0 30px"
            display="flex "
            justifyContent="space-between"
            alignItems="center"
          >
            <Box>
              <Typography
                fontWeight="bold"
                sx={{ color: colors.grey[100] }}
                fontSize={titleFontSize}
                color={colors.grey[100]}
              >
                Force vs Time
              </Typography>
              <Typography
                fontSize={subtitleFontSize}
                color={colors.greenAccent[500]}
              >
                {/* number */}
              </Typography>
            </Box>
            <Box>
              <IconButton onClick={handleDownload}>
                <DownloadOutlinedIcon
                  sx={{ fontSize: "26px", color: colors.greenAccent[500] }}
                />
              </IconButton>
            </Box>
          </Box>
          <LineChart ref={setChartRef} min={0} max={10} />
        </Box>
      ),
    },
    {
      id: 8,
      gridColumn: "span 12",
      gridRow: "span 3",
      content: (
        <Box width="100%">
          <Box
            mt="25px"
            p="0 30px"
            display="flex "
            justifyContent="space-between"
            alignItems="center"
          >
            <Box>
              <Typography
                fontWeight="bold"
                sx={{ color: colors.grey[100] }}
                fontSize={titleFontSize}
                color={colors.grey[100]}
              >
                Z vs Time
              </Typography>
              <Typography
                fontSize={subtitleFontSize}
                color={colors.greenAccent[500]}
              >
                {/* number */}
              </Typography>
            </Box>
            <Box>
              <IconButton onClick={handleDownload}>
                <DownloadOutlinedIcon
                  sx={{ fontSize: "26px", color: colors.greenAccent[500] }}
                />
              </IconButton>
            </Box>
          </Box>
          <LineChart dataset="displacement" ref={setChartRef} min={0} max={10} />
        </Box>
      ),
    },
    {
      id: 1,
      content: <ControlButton type="connection" />,
      gridColumn: "span 2",
      gridRow: "span 1",
    },
    {
      id: 2,
      content: (
        <ControlButton
          type="save"
          saveEnabled={saveEnabled}
          setSaveEnabled={setSaveEnabled}
        />
      ),
      gridColumn: "span 2",
      gridRow: "span 1",
    },
    {
      id: 3,
      content: (
        <StatBox
          measurementColor="#006666"
          title="Displacement Last Value"
          subtitle={`${transformedData.series1?.[0]?.value || "-"} 
      cm`}
        />
      ),
      gridColumn: "span 2",
      gridRow: "span 1",
      lineColor: "#009688",
      areaColor: "rgba(0,150,136,0.2)",
      data: transformedData.series1 || [],
    },
    {
      id: 4,
      content: (
        <StatBox
          measurementColor="#D35400"
          title="Force Last Value"
          subtitle={`${transformedData.series1?.[0]?.value || "-"} 
      N`}
        />
      ),
      gridColumn: "span 2",
      gridRow: "span 1",
      lineColor: "#FF9800",
      areaColor: " rgba(255,152,0,0.2)",
      data: transformedData.series1 || [],
    },
  ]);
  const updatedBoxes = boxes.map((box) => {
    if (box.id === 10) {
      // Keeps jog control button dimensions unchanged after moving controls.
      const cameraJogControlSize = 52;

      // Keeps icon dimensions unchanged for camera card jog controls.
      const cameraJogIconSize = 24;

      // Shared style for directional jog icon buttons in camera card.
      const cameraJogBtnStyle = {
        backgroundColor: colors.greenAccent[700],
        borderRadius: "6px",
        border: `1px solid ${colors.greenAccent[500]}`,
        color: colors.grey[100],
        width: cameraJogControlSize,
        height: cameraJogControlSize,
        "&:hover": { backgroundColor: colors.greenAccent[600] },
        "&:disabled": { opacity: 0.35 },
      };

      // Jog step button style in camera card — highlighted when active.
      const cameraStepBtnStyle = (step) => ({
        minWidth: "52px",
        fontSize: "14px",
        padding: "6px 10px",
        backgroundColor: jogStep === step ? colors.greenAccent[700] : "transparent",
        color: colors.grey[100],
        border: `1px solid ${colors.greenAccent[500]}`,
        "&:hover": { backgroundColor: colors.greenAccent[600] },
      });
      return {
        ...box,
        content: (
          <Box width={isSmallScreen ? "100%" : "80%"} p="12px" height="100%" display="flex" flexDirection="column" gap="8px" sx={{ overflow: "hidden", boxSizing: "border-box" }}>
            <Typography
              fontWeight="bold"
              sx={{ color: colors.grey[100] }}
              fontSize={titleFontSize}
            >
              Camera View
            </Typography>
            {/* Always splits the camera card vertically: left = controls, right = live feed. */}
            <Box
              display="flex"
              flexDirection="row"
              gap="0px"
              flexGrow={1}
              minHeight={0}
              sx={{ overflow: "hidden" }}
            >
              {/* Left column: step selector and XY/Z jog pads. */}
              <Box
                display="flex"
                flexDirection="column"
                gap="8px"
                sx={{
                  flex: "0 0 42%",
                  minWidth: 0,
                  overflow: "hidden",
                  pr: "10px",
                }}
              >
                {/* Step size selector buttons */}
                <Box display="flex" alignItems="center" gap="6px" flexWrap="wrap">
                  <Typography fontSize="12px" sx={{ color: colors.grey[400] }}>Step:</Typography>
                  {[0.1, 1, 10].map((step) => (
                    <Button key={step} size="small" sx={cameraStepBtnStyle(step)} onClick={() => setJogStep(step)}>
                      {step}
                    </Button>
                  ))}
                  <Typography fontSize="12px" sx={{ color: colors.grey[400] }}>mm</Typography>
                </Box>

                {/* XY and Z jog pads aligned side by side */}
                <Box display="flex" gap="8px" alignItems="flex-start" flexWrap="wrap">
                  {/* Head XY jog pad */}
                  <Box display="flex" flexDirection="column" alignItems="center" gap="4px">
                    <Typography fontSize="11px" sx={{ color: colors.grey[400] }}>Head XY</Typography>
                    <Box display="grid" gridTemplateColumns={`repeat(3, ${cameraJogControlSize}px)`} gridTemplateRows={`repeat(3, ${cameraJogControlSize}px)`} gap="4px">
                      <Box />
                      <IconButton size="small" disabled={printerActionInProgress} onClick={() => handleJogAxis("Y", 1)} sx={cameraJogBtnStyle}>
                        <ArrowUpwardIcon sx={{ fontSize: cameraJogIconSize }} />
                      </IconButton>
                      <Box />
                      <IconButton size="small" disabled={printerActionInProgress} onClick={() => handleJogAxis("X", -1)} sx={cameraJogBtnStyle}>
                        <ArrowBackIcon sx={{ fontSize: cameraJogIconSize }} />
                      </IconButton>
                      <Box display="flex" alignItems="center" justifyContent="center" sx={{ backgroundColor: colors.primary[400], borderRadius: "6px" }}>
                        <Typography fontSize="11px" sx={{ color: colors.grey[400] }}>XY</Typography>
                      </Box>
                      <IconButton size="small" disabled={printerActionInProgress} onClick={() => handleJogAxis("X", 1)} sx={cameraJogBtnStyle}>
                        <ArrowForwardIcon sx={{ fontSize: cameraJogIconSize }} />
                      </IconButton>
                      <Box />
                      <IconButton size="small" disabled={printerActionInProgress} onClick={() => handleJogAxis("Y", -1)} sx={cameraJogBtnStyle}>
                        <ArrowDownwardIcon sx={{ fontSize: cameraJogIconSize }} />
                      </IconButton>
                      <Box />
                    </Box>
                  </Box>

                  {/* Bed Z jog pad */}
                  <Box display="flex" flexDirection="column" alignItems="center" gap="4px">
                    <Typography fontSize="11px" sx={{ color: colors.grey[400] }}>Bed Z</Typography>
                    <Box display="flex" flexDirection="column" alignItems="center" gap="4px">
                      <IconButton size="small" disabled={printerActionInProgress} onClick={() => handleJogAxis("Z", -1)} sx={cameraJogBtnStyle}>
                        <ArrowUpwardIcon sx={{ fontSize: cameraJogIconSize }} />
                      </IconButton>
                      <Box display="flex" alignItems="center" justifyContent="center" sx={{ width: cameraJogControlSize, height: cameraJogControlSize, backgroundColor: colors.primary[400], borderRadius: "6px" }}>
                        <Typography fontSize="11px" sx={{ color: colors.grey[400] }}>Z</Typography>
                      </Box>
                      <IconButton size="small" disabled={printerActionInProgress} onClick={() => handleJogAxis("Z", 1)} sx={cameraJogBtnStyle}>
                        <ArrowDownwardIcon sx={{ fontSize: cameraJogIconSize }} />
                      </IconButton>
                    </Box>
                  </Box>
                </Box>
              </Box>

              {/* Vertical divider between the controls column and the camera feed. */}
              <Box
                sx={{
                  width: "2px",
                  backgroundColor: "#808080",
                  alignSelf: "stretch",
                  borderRadius: "2px",
                  flexShrink: 0,
                }}
              />

              {/* Right column: live camera feed fills the remaining space. */}
              <Box
                display="flex"
                flexDirection="column"
                gap="6px"
                sx={{
                  flex: "1 1 0",
                  minWidth: 0,
                  pl: "10px",
                }}
              >
                <Typography fontSize="12px" sx={{ color: colors.grey[400] }}>
                  Live feed
                </Typography>
                {/* Width 100% ensures the feed container spans the full right-column width. */}
                <Box flexGrow={1} minHeight={0} display="flex" alignItems="center" justifyContent="center" width="100%">
                  <img
                    src={`${VIDEO_BASE_URL}/video`}
                    alt="Live stream"
                    style={{ width: "100%", height: "100%", objectFit: "cover", borderRadius: "4px" }}
                  />
                </Box>
              </Box>
            </Box>
          </Box>
        ),
      };
    } else if (box.id === 9) {
      // Shared style for utility action buttons (Home, Connect, Disconnect).
      const utilBtnStyle = {
        fontSize: "13px",
        padding: "10px 12px",
        color: colors.grey[100],
        border: `1px solid ${colors.greenAccent[500]}`,
        backgroundColor: colors.greenAccent[800] ?? colors.greenAccent[700],
        "&:hover": { backgroundColor: colors.greenAccent[600] },
        "&:disabled": { opacity: 0.35 },
        minWidth: 0,
        minHeight: 56,
      };

      // Style for the emergency stop button — prominent red to signal danger.
      const eStopBtnStyle = {
        fontSize: "13px",
        padding: "10px 12px",
        color: "#fff",
        border: "1px solid #c62828",
        backgroundColor: "#c62828",
        "&:hover": { backgroundColor: "#b71c1c" },
        minWidth: 0,
        minHeight: 56,
      };

      // Style for the connect button so connection state is visible in the merged card.
      const connectBtnStyle = {
        fontSize: "13px",
        padding: "10px 12px",
        color: colors.grey[100],
        border: `1px solid ${colors.greenAccent[500]}`,
        backgroundColor: printerConnected ? colors.greenAccent[700] : "transparent",
        "&:hover": { backgroundColor: colors.greenAccent[600] },
        "&:disabled": { opacity: 0.35 },
        minWidth: 0,
        minHeight: 56,
      };

      // Style for the disconnect button so users can quickly close the printer port.
      const disconnectBtnStyle = {
        fontSize: "13px",
        padding: "10px 12px",
        color: colors.grey[100],
        border: "1px solid #c62828",
        backgroundColor: "transparent",
        "&:hover": { backgroundColor: "#c62828" },
        "&:disabled": { opacity: 0.35 },
        minWidth: 0,
        minHeight: 56,
      };

      // Shared full-width button sizing keeps the three top actions aligned in one row.
      const printerActionButtonStyle = {
        width: "100%",
        minHeight: 64,
      };

      // Shared panel styling keeps the controls and live status blocks visually balanced.
      const printerPanelSectionStyle = {
        backgroundColor: colors.primary[400],
        borderRadius: "8px",
        minHeight: 0,
        boxSizing: "border-box",
      };

      // Shared status card styling makes each status tile stretch to evenly fill the column.
      const printerStatusCardStyle = {
        ...printerPanelSectionStyle,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        flex: 1,
        p: "10px 12px",
      };

      return {
        ...box,
        content: (
          // Fills the full draggable card area and allows content to scale cleanly.
          <Box
            p="12px"
            display="flex"
            flexDirection="column"
            gap="8px"
            height="100%"
            width="100%"
            minHeight={0}
            sx={{ overflow: "hidden", boxSizing: "border-box" }}
          >
            {/* Section title */}
            <Typography fontWeight="bold" sx={{ color: colors.grey[100] }} fontSize={titleFontSize}>
              Printer Controls & Status
            </Typography>

            {/* Splits card content into control panel (left) and status panel (right). */}
            <Box
              display="flex"
              flexDirection={isSmallScreen ? "column" : "row"}
              gap="12px"
              flexGrow={1}
              minHeight={0}
            >
              {/* Left section: all command controls and jog actions. */}
              <Box
                display="flex"
                flexDirection="column"
                gap="10px"
                minHeight={0}
                sx={{
                  ...printerPanelSectionStyle,
                  flex: isSmallScreen ? "1 1 auto" : "0 0 58%",
                  overflow: "hidden",
                  p: "10px",
                }}
              >
                {/* Quick-action row keeps connect, home, and E-stop aligned in a single row. */}
                <Box
                  display="grid"
                  gridTemplateColumns="repeat(3, minmax(0, 1fr))"
                  gridAutoRows="minmax(64px, auto)"
                  gap="10px"
                  flexGrow={1}
                  minHeight={0}
                >
                  <Button
                    disabled={printerActionInProgress}
                    onClick={printerConnected ? handleDisconnectPrinter : handleConnectPrinter}
                    startIcon={
                      printerConnected
                        ? <LinkOffIcon sx={{ fontSize: 14 }} />
                        : <LinkIcon sx={{ fontSize: 14 }} />
                    }
                    sx={{
                      ...(printerConnected ? disconnectBtnStyle : connectBtnStyle),
                      ...printerActionButtonStyle,
                    }}
                  >
                    {printerConnected ? "Disconnect" : "Connect"}
                  </Button>
                  <Button
                    disabled={printerActionInProgress}
                    onClick={handleHomePrinter}
                    startIcon={<HomeIcon sx={{ fontSize: 16 }} />}
                    sx={{ ...utilBtnStyle, ...printerActionButtonStyle }}
                  >
                    Home All
                  </Button>
                  <Button
                    disabled={printerActionInProgress}
                    onClick={handleEmergencyStop}
                    startIcon={<StopIcon sx={{ fontSize: 16 }} />}
                    sx={{ ...eStopBtnStyle, ...printerActionButtonStyle }}
                  >
                    E-STOP
                  </Button>
                </Box>
              </Box>

              {/* Vertical separator between printer controls and status values. */}
              <Box
                sx={{
                  width: isSmallScreen ? "100%" : "2px",
                  height: isSmallScreen ? "2px" : "auto",
                  backgroundColor: "#808080",
                  alignSelf: "stretch",
                  borderRadius: "2px",
                }}
              />

              {/* Right section: Cmd + Bed Status on the same top row, Position spanning full width below. */}
              <Box
                display="flex"
                flexDirection="column"
                gap="8px"
                minHeight={0}
                sx={{ flex: isSmallScreen ? "1 1 auto" : "0 0 42%" }}
              >
                {/* Top row: Cmd card (left) and Bed Status card (right) side by side. */}
                <Box display="flex" flexDirection="row" gap="8px" minHeight={0}>
                  <Box sx={{ ...printerStatusCardStyle, flex: 1, minWidth: 0 }}>
                    <Box display="flex" alignItems="center" gap="6px">
                      <MyLocationIcon sx={{ fontSize: 14, color: colors.greenAccent[400] }} />
                      <Typography fontSize="12px" sx={{ color: colors.grey[300] }}>
                        Cmd
                      </Typography>
                    </Box>
                    <Typography fontSize="14px" fontWeight="bold" sx={{ color: colors.greenAccent[400], mt: "4px" }}>
                      {printerActionStatus}
                    </Typography>
                  </Box>

                  <Box sx={{ ...printerStatusCardStyle, flex: 1, minWidth: 0 }}>
                    <Box display="flex" alignItems="center" gap="6px">
                      <ThermostatIcon sx={{ fontSize: 14, color: colors.redAccent[400] }} />
                      <Typography fontSize="12px" sx={{ color: colors.grey[300] }}>
                        Bed Status
                      </Typography>
                    </Box>
                    <Typography fontSize="14px" fontWeight="bold" sx={{ color: colors.redAccent[300], mt: "4px" }}>
                      {bedTemperature !== null ? `${bedTemperature.toFixed(1)} °C` : "—"}
                    </Typography>
                  </Box>
                </Box>

                {/* Bottom row: Position spanning the full status column width. */}
                <Box sx={printerStatusCardStyle}>
                  <Box display="flex" alignItems="center" gap="6px">
                    <MyLocationIcon sx={{ fontSize: 14, color: colors.greenAccent[400] }} />
                    <Typography fontSize="12px" sx={{ color: colors.grey[300] }}>
                      Position
                    </Typography>
                  </Box>
                  <Typography fontSize="14px" fontWeight="bold" sx={{ color: colors.greenAccent[400], mt: "4px" }}>
                    X:{printerPosition.x !== null && printerPosition.x !== undefined ? Number(printerPosition.x).toFixed(1) : "—"} / Y:{printerPosition.y !== null && printerPosition.y !== undefined ? Number(printerPosition.y).toFixed(1) : "—"} / Z:{printerPosition.z !== null && printerPosition.z !== undefined ? Number(printerPosition.z).toFixed(1) : "—"}
                  </Typography>
                </Box>
              </Box>
            </Box>
          </Box>
        ),
      };
    } else if (box.id === 3) {
      return {
        ...box,
        data: series1Data,
        content: (
          <StatBox
            title="Displacement"
            subtitle={`${
              series1Data?.[series1Data.length - 1]?.value
                ? series1Data[series1Data.length - 1].value.toFixed(2)
                : "-"
            } cm`}
            icon={<SwapHorizIcon style={{ color: "#009688", fontSize: 28 }} />}
          />
        ),
      };
    } else if (box.id === 4) {
      return {
        ...box,
        data: series2Data,
        content: (
          <StatBox
            title="Force"
            subtitle={`${
              series2Data?.[series2Data.length - 1]?.value
                ? series2Data[series2Data.length - 1].value.toFixed(2)
                : "-"
            } cm`}
            icon={<BoltIcon style={{ color: "#FF9800 ", fontSize: 28 }} />}
          />
        ),
      };
    }

    // "Received data / Received points" widget is intentionally disabled and
    // replaced with printer control actions above.
    return box;
  });

  const updateGridColumns = () => {
    const screenWidth = window.innerWidth;
    // Tracks low-height 7-inch layouts so key cards can switch to compact spans.
    const isCompactPanel = screenWidth <= 1024 && window.innerHeight <= 700;
    setBoxes((prevBoxes) =>
      prevBoxes.map((box) => ({
        ...box,
        gridColumn:
        screenWidth <= 800
        ? [1, 2, 3, 4].includes(box.id)
          ? "span 6"
          : [9, 10].includes(box.id)
          ? "span 12"
          : box.gridColumn
        : [1, 2, 3, 4].includes(box.id)
        ? isCompactPanel
          ? "span 3"
          : "span 2"
        : [9, 10, 7, 8].includes(box.id) && isCompactPanel
        ? "span 12"
        : box.id === 9
        ? "span 8"
        : box.id === 10
        ? "span 4"
        : box.gridColumn,
        gridRow:
        box.id === 10 && isCompactPanel
        ? "span 3"
        : box.id === 10
        ? "span 2"
        // Printer controls card stays compact at span 2 regardless of breakpoint.
        : box.id === 9
        ? "span 2"
        : box.gridRow,
      }))
    );
  };

  useEffect(() => {
    // Initial check
    updateGridColumns();

    // Add event listener for resizing
    window.addEventListener("resize", updateGridColumns);

    // Cleanup the event listener on component unmount
    return () => {
      window.removeEventListener("resize", updateGridColumns);
    };
  }, []);

  return (
    <Box m={dashboardOuterMargin}>
      {/* HEADER */}
      {showDashboardHeader && (<Box display="flex" justifyContent="space-between" alignItems="center">
        <Header title="DASHBOARD" subtitle="Welcome to your dashboard" />

        <Box>
          <Button
            onClick={downloadDeviceData}
            sx={{
              backgroundColor: colors.blueAccent[700],
              color: colors.grey[100],
              fontSize: "14px",
              fontWeight: "bold",
              padding: "10px 20px",
            }}
          >
            <DownloadOutlinedIcon sx={{ mr: "10px" }} />
            Download Reports
          </Button>
        </Box>
      </Box> )}

      {/* GRID & CHARTS */}
      <Box
        display="grid"
        gridTemplateColumns="repeat(12, 1fr)"
        gridAutoRows={dashboardGridAutoRows}
        gap={dashboardGridGap}
      >
        {/* Render all boxes as draggable */}
        {updatedBoxes.map((box) => (
          <DraggableBox
            key={box.id}
            id={box.id}
            onDrop={handleDrop}
            backgroundColor={colors.primary[400]}
            handleDelete={handleDelete}
            gridColumn={box.gridColumn}
            gridRow={box.gridRow}
            onHover={handleHover}
            lineColor={box.lineColor}
            areaColor={box.areaColor}
            data={box.data}
          >
            {box.content}
          </DraggableBox>
        ))}
      </Box>
    </Box>
  );
};

export default Dashboard;
