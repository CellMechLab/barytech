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
import DraggableBox from "./DraggableBox";
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
import { BACKEND_BASE_URL, VIDEO_BASE_URL } from "../../config/endpoints";

const Dashboard = () => {
  const backendApiUrl = BACKEND_BASE_URL;
  const theme = useTheme();
  const colors = tokens(theme.palette.mode);
  const [totalDataPoints, setTotalDataPoints] = useState(0);
  const { dataBuffer } = useContext(WebSocketContext);
  const [saveEnabled, setSaveEnabled] = useState(false);

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

  const { downloadDeviceData } = useDeviceDataExport(backendApiUrl);

  const handleDataPointCountChange = (count) => {
    setTotalDataPoints(count);
  };

  // ─── Breakpoints ───────────────────────────────────────────────────────────
  // Covers anything ≤ 520 px (phones like iPhone SE, small Androids).
  const isExtraSmallScreen = useMediaQuery("(max-width:520px)");
  // NEW — specifically targets 5-inch portrait devices (e.g. 720 × 1280).
  // Sits between isExtraSmallScreen and isMediumScreen so it gets its own
  // sizing values instead of accidentally inheriting the full-desktop "20px" fallback.
  const isFiveInch = useMediaQuery("(max-width:720px)");
  // General "phone or small tablet" umbrella used for stacking layout decisions.
  const isSmallScreen = useMediaQuery("(max-width:800px)");
  const isMediumScreen = useMediaQuery(
    "(min-width:800px) and (max-width:1024px)"
  );
  const isLargeScreen = useMediaQuery(
    "(min-width:1025px) and (max-width:1440px)"
  );
  // 7-inch landscape panels (e.g. 1024 × 600).
  const isSevenInchDisplay = useMediaQuery(
    "(max-width:1024px) and (max-height:700px)"
  );

  // ─── Typography ────────────────────────────────────────────────────────────
  const titleFontSize = isSmallScreen
    ? "13px"
    : isSevenInchDisplay
    ? "15px"
    : isMediumScreen
    ? "16px"
    : isLargeScreen
    ? "18px"
    : "20px";

  const subtitleFontSize = isSmallScreen
    ? "12px"
    : isSevenInchDisplay
    ? "14px"
    : isMediumScreen
    ? "16px"
    : isLargeScreen
    ? "15px"
    : "22px";

  // ─── Layout helpers ────────────────────────────────────────────────────────
  const showDashboardHeader = !isSmallScreen && !isSevenInchDisplay;

  // FIX: previously jumped from isExtraSmallScreen (≤520) straight to "20px",
  // leaving 5-inch (720 px) devices with full desktop margins.
  const dashboardOuterMargin = isExtraSmallScreen
    ? "6px"
    : isFiveInch
    ? "10px"
    : isSevenInchDisplay
    ? "10px"
    : "20px";

  // FIX: same issue with gap — 5-inch was getting the 20 px desktop gap.
  const dashboardGridGap = isExtraSmallScreen
    ? "6px"
    : isFiveInch
    ? "8px"
    : isSevenInchDisplay
    ? "12px"
    : "20px";

  // FIX: tighter rows for 5-inch portrait so content doesn't over-expand vertically.
  const dashboardGridAutoRows = isSevenInchDisplay
    ? "minmax(118px, auto)"
    : isFiveInch
    ? "minmax(82px, auto)"
    : isSmallScreen
    ? "minmax(100px, auto)"
    : "minmax(140px, auto)";

  const [transformedData, setTransformedData] = useState({
    series1: [],
    series2: [],
  });
  const [series1Data, setSeries1Data] = useState([]);
  const [series2Data, setSeries2Data] = useState([]);

  useEffect(() => {
    if (chartRef.current) {
      const data = chartRef.current.transformData(dataBuffer);
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
      chartRef.current.downloadChart();
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
    [fromBox.gridColumn, toBox.gridColumn] = [toBox.gridColumn, fromBox.gridColumn];
    [fromBox.gridRow, toBox.gridRow] = [toBox.gridRow, fromBox.gridRow];
    setBoxes(newBoxes);
  };

  const handleHover = (fromId, toId) => {
    const newBoxes = [...boxes];
    const fromIndex = newBoxes.findIndex((box) => box.id === fromId);
    const toIndex = newBoxes.findIndex((box) => box.id === toId);
    if (fromIndex === -1 || toIndex === -1) return;
    [newBoxes[fromIndex], newBoxes[toIndex]] = [newBoxes[toIndex], newBoxes[fromIndex]];
    setBoxes(newBoxes);
  };

  const handleDelete = (id) => {
    setBoxes((prevBoxes) => prevBoxes.filter((box) => box.id !== id));
  };

  const [boxes, setBoxes] = useState([
    {
      id: 9,
      gridColumn: "span 8",
      gridRow: "span 2",
      content: null,
    },
    {
      id: 10,
      gridColumn: "span 4",
      gridRow: "span 2",
      content: null,
    },
    {
      id: 7,
      gridColumn: "span 12",
      gridRow: "span 3",
      content: (
        <Box width="100%" height="100%" display="flex" flexDirection="column" sx={{ minHeight: 0, overflow: "hidden" }}>
          <Box
            mt={isExtraSmallScreen ? "6px" : isFiveInch ? "8px" : isSmallScreen ? "10px" : "18px"}
            px={isExtraSmallScreen ? "8px" : isFiveInch ? "10px" : isSmallScreen ? "14px" : "24px"}
            display="flex"
            justifyContent="space-between"
            alignItems="center"
            sx={{ flexShrink: 0 }}
          >
            <Box>
              <Typography
                fontWeight="bold"
                sx={{ color: colors.grey[100], fontSize: "clamp(12px, 1.4vw, 20px)" }}
              >
                Force vs Time
              </Typography>
            </Box>
            <Box>
              <IconButton onClick={handleDownload}>
                <DownloadOutlinedIcon
                  sx={{ fontSize: "clamp(16px, 2vw, 26px)", color: colors.greenAccent[500] }}
                />
              </IconButton>
            </Box>
          </Box>
          <Box flexGrow={1} sx={{ minHeight: 0, overflow: "hidden" }}>
            <LineChart ref={setChartRef} min={0} max={10} />
          </Box>
        </Box>
      ),
    },
    {
      id: 8,
      gridColumn: "span 12",
      gridRow: "span 3",
      content: (
        <Box width="100%" height="100%" display="flex" flexDirection="column" sx={{ minHeight: 0, overflow: "hidden" }}>
          <Box
            mt={isExtraSmallScreen ? "6px" : isFiveInch ? "8px" : isSmallScreen ? "10px" : "18px"}
            px={isExtraSmallScreen ? "8px" : isFiveInch ? "10px" : isSmallScreen ? "14px" : "24px"}
            display="flex"
            justifyContent="space-between"
            alignItems="center"
            sx={{ flexShrink: 0 }}
          >
            <Box>
              <Typography
                fontWeight="bold"
                sx={{ color: colors.grey[100], fontSize: "clamp(12px, 1.4vw, 20px)" }}
              >
                Z vs Time
              </Typography>
            </Box>
            <Box>
              <IconButton onClick={handleDownload}>
                <DownloadOutlinedIcon
                  sx={{ fontSize: "clamp(16px, 2vw, 26px)", color: colors.greenAccent[500] }}
                />
              </IconButton>
            </Box>
          </Box>
          <Box flexGrow={1} sx={{ minHeight: 0, overflow: "hidden" }}>
            <LineChart dataset="displacement" ref={setChartRef} min={0} max={10} />
          </Box>
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
          subtitle={`${transformedData.series1?.[0]?.value || "-"} cm`}
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
          subtitle={`${transformedData.series1?.[0]?.value || "-"} N`}
        />
      ),
      gridColumn: "span 2",
      gridRow: "span 1",
      lineColor: "#FF9800",
      areaColor: "rgba(255,152,0,0.2)",
      data: transformedData.series1 || [],
    },
  ]);

  const updatedBoxes = boxes.map((box) => {
    if (box.id === 10) {
      // ── Jog control sizing ─────────────────────────────────────────────────
      // 5-inch (720 px): 40 px gives a comfortable touch target without clipping.
      const cameraJogControlSize = isExtraSmallScreen
        ? 34
        : isFiveInch
        ? 40
        : isSmallScreen
        ? 42
        : isSevenInchDisplay
        ? 44
        : 52;

      const cameraJogIconSize = isExtraSmallScreen
        ? 16
        : isFiveInch
        ? 18
        : isSmallScreen
        ? 20
        : 24;

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

      const cameraStepBtnStyle = (step) => ({
        minWidth: isExtraSmallScreen ? "38px" : isFiveInch ? "42px" : "52px",
        fontSize: isExtraSmallScreen ? "11px" : isFiveInch ? "12px" : "14px",
        padding: isExtraSmallScreen ? "3px 6px" : isFiveInch ? "4px 8px" : "6px 10px",
        backgroundColor: jogStep === step ? colors.greenAccent[700] : "transparent",
        color: colors.grey[100],
        border: `1px solid ${colors.greenAccent[500]}`,
        "&:hover": { backgroundColor: colors.greenAccent[600] },
      });

      return {
        ...box,
        content: (
          <Box
            width="100%"
            p={isExtraSmallScreen ? "6px" : isFiveInch ? "10px" : "12px"}
            height="100%"
            display="flex"
            flexDirection="column"
            gap={isFiveInch ? "6px" : "8px"}
            sx={{ overflow: "hidden", boxSizing: "border-box" }}
          >
            <Typography
              fontWeight="bold"
              sx={{ color: colors.grey[100] }}
              fontSize={titleFontSize}
            >
              Camera View
            </Typography>

            <Box
              display="flex"
              flexDirection={isSmallScreen ? "column" : "row"}
              gap={isSmallScreen ? "8px" : "0px"}
              flexGrow={1}
              minHeight={0}
              sx={{ overflow: "hidden" }}
            >
              {/* Left column: step selector + jog pads */}
              <Box
                display="flex"
                flexDirection="column"
                gap="6px"
                sx={{
                  flex: isSmallScreen ? "1 1 auto" : "0 0 42%",
                  minWidth: 0,
                  overflow: "hidden",
                  pr: isSmallScreen ? "0" : "10px",
                }}
              >
                {/* Step size selector */}
                <Box display="flex" alignItems="center" gap="4px" flexWrap="wrap">
                  <Typography fontSize="11px" sx={{ color: colors.grey[400] }}>Step:</Typography>
                  {[0.1, 1, 10].map((step) => (
                    <Button key={step} size="small" sx={cameraStepBtnStyle(step)} onClick={() => setJogStep(step)}>
                      {step}
                    </Button>
                  ))}
                  <Typography fontSize="11px" sx={{ color: colors.grey[400] }}>mm</Typography>
                </Box>

                {/* XY + Z jog pads */}
                <Box display="flex" gap="8px" alignItems="flex-start" flexWrap="wrap">
                  {/* Head XY */}
                  <Box display="flex" flexDirection="column" alignItems="center" gap="4px">
                    <Typography fontSize="10px" sx={{ color: colors.grey[400] }}>Head XY</Typography>
                    <Box
                      display="grid"
                      gridTemplateColumns={`repeat(3, ${cameraJogControlSize}px)`}
                      gridTemplateRows={`repeat(3, ${cameraJogControlSize}px)`}
                      gap="3px"
                    >
                      <Box />
                      <IconButton size="small" disabled={printerActionInProgress} onClick={() => handleJogAxis("Y", 1)} sx={cameraJogBtnStyle}>
                        <ArrowUpwardIcon sx={{ fontSize: cameraJogIconSize }} />
                      </IconButton>
                      <Box />
                      <IconButton size="small" disabled={printerActionInProgress} onClick={() => handleJogAxis("X", -1)} sx={cameraJogBtnStyle}>
                        <ArrowBackIcon sx={{ fontSize: cameraJogIconSize }} />
                      </IconButton>
                      <Box display="flex" alignItems="center" justifyContent="center" sx={{ backgroundColor: colors.primary[400], borderRadius: "6px" }}>
                        <Typography fontSize="10px" sx={{ color: colors.grey[400] }}>XY</Typography>
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

                  {/* Bed Z */}
                  <Box display="flex" flexDirection="column" alignItems="center" gap="4px">
                    <Typography fontSize="10px" sx={{ color: colors.grey[400] }}>Bed Z</Typography>
                    <Box display="flex" flexDirection="column" alignItems="center" gap="3px">
                      <IconButton size="small" disabled={printerActionInProgress} onClick={() => handleJogAxis("Z", -1)} sx={cameraJogBtnStyle}>
                        <ArrowUpwardIcon sx={{ fontSize: cameraJogIconSize }} />
                      </IconButton>
                      <Box display="flex" alignItems="center" justifyContent="center" sx={{ width: cameraJogControlSize, height: cameraJogControlSize, backgroundColor: colors.primary[400], borderRadius: "6px" }}>
                        <Typography fontSize="10px" sx={{ color: colors.grey[400] }}>Z</Typography>
                      </Box>
                      <IconButton size="small" disabled={printerActionInProgress} onClick={() => handleJogAxis("Z", 1)} sx={cameraJogBtnStyle}>
                        <ArrowDownwardIcon sx={{ fontSize: cameraJogIconSize }} />
                      </IconButton>
                    </Box>
                  </Box>
                </Box>
              </Box>

              {/* Divider */}
              <Box
                sx={{
                  width: isSmallScreen ? "100%" : "2px",
                  height: isSmallScreen ? "2px" : "auto",
                  backgroundColor: "#808080",
                  alignSelf: "stretch",
                  borderRadius: "2px",
                  flexShrink: 0,
                }}
              />

              {/* Right column: live camera feed */}
              <Box
                display="flex"
                flexDirection="column"
                gap="4px"
                sx={{
                  flex: "1 1 0",
                  minWidth: 0,
                  pl: isSmallScreen ? "0px" : "10px",
                }}
              >
                <Typography fontSize="11px" sx={{ color: colors.grey[400] }}>Live feed</Typography>
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
      // ── Printer controls button styles ─────────────────────────────────────
      const utilBtnStyle = {
        fontSize: isExtraSmallScreen ? "11px" : isFiveInch ? "12px" : "13px",
        padding: isExtraSmallScreen ? "6px 8px" : isFiveInch ? "8px 10px" : "10px 12px",
        color: colors.grey[100],
        border: `1px solid ${colors.greenAccent[500]}`,
        backgroundColor: colors.greenAccent[800] ?? colors.greenAccent[700],
        "&:hover": { backgroundColor: colors.greenAccent[600] },
        "&:disabled": { opacity: 0.35 },
        minWidth: 0,
        // FIX: reduce tap-target height on 5-inch; 48px still meets accessibility minimums.
        minHeight: isExtraSmallScreen ? 44 : isFiveInch ? 48 : 56,
      };

      const eStopBtnStyle = {
        fontSize: isExtraSmallScreen ? "11px" : isFiveInch ? "12px" : "13px",
        padding: isExtraSmallScreen ? "6px 8px" : isFiveInch ? "8px 10px" : "10px 12px",
        color: "#fff",
        border: "1px solid #c62828",
        backgroundColor: "#c62828",
        "&:hover": { backgroundColor: "#b71c1c" },
        minWidth: 0,
        minHeight: isExtraSmallScreen ? 44 : isFiveInch ? 48 : 56,
      };

      const connectBtnStyle = {
        fontSize: isExtraSmallScreen ? "11px" : isFiveInch ? "12px" : "13px",
        padding: isExtraSmallScreen ? "6px 8px" : isFiveInch ? "8px 10px" : "10px 12px",
        color: colors.grey[100],
        border: `1px solid ${colors.greenAccent[500]}`,
        backgroundColor: printerConnected ? colors.greenAccent[700] : "transparent",
        "&:hover": { backgroundColor: colors.greenAccent[600] },
        "&:disabled": { opacity: 0.35 },
        minWidth: 0,
        minHeight: isExtraSmallScreen ? 44 : isFiveInch ? 48 : 56,
      };

      const disconnectBtnStyle = {
        fontSize: isExtraSmallScreen ? "11px" : isFiveInch ? "12px" : "13px",
        padding: isExtraSmallScreen ? "6px 8px" : isFiveInch ? "8px 10px" : "10px 12px",
        color: colors.grey[100],
        border: "1px solid #c62828",
        backgroundColor: "transparent",
        "&:hover": { backgroundColor: "#c62828" },
        "&:disabled": { opacity: 0.35 },
        minWidth: 0,
        minHeight: isExtraSmallScreen ? 44 : isFiveInch ? 48 : 56,
      };

      // FIX: reduce minHeight — at 720 px the 64 px button rows were wasting vertical space.
      const printerActionButtonStyle = {
        width: "100%",
        minHeight: isExtraSmallScreen ? 44 : isFiveInch ? 48 : isSmallScreen ? 52 : 64,
      };

      const printerPanelSectionStyle = {
        backgroundColor: colors.primary[400],
        borderRadius: "8px",
        minHeight: 0,
        boxSizing: "border-box",
      };

      const printerStatusCardStyle = {
        ...printerPanelSectionStyle,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        flex: 1,
        p: isFiveInch ? "8px 10px" : "10px 12px",
      };

      return {
        ...box,
        content: (
          <Box
            p={isFiveInch ? "10px" : "12px"}
            display="flex"
            flexDirection="column"
            gap={isFiveInch ? "6px" : "8px"}
            height="100%"
            width="100%"
            minHeight={0}
            sx={{ overflow: "hidden", boxSizing: "border-box" }}
          >
            <Typography fontWeight="bold" sx={{ color: colors.grey[100] }} fontSize={titleFontSize}>
              Printer Controls & Status
            </Typography>

            <Box
              display="flex"
              flexDirection={isSmallScreen ? "column" : "row"}
              gap={isFiveInch ? "8px" : "12px"}
              flexGrow={1}
              minHeight={0}
            >
              {/* Left section: command controls */}
              <Box
                display="flex"
                flexDirection="column"
                gap={isFiveInch ? "6px" : "10px"}
                minHeight={0}
                sx={{
                  ...printerPanelSectionStyle,
                  flex: isSmallScreen ? "1 1 auto" : "0 0 58%",
                  overflow: "hidden",
                  p: isFiveInch ? "8px" : "10px",
                }}
              >
                {/* Quick-action row: Connect / Home / E-STOP
                    FIX — on 5-inch (720 px) we can fit all three in one row (3 columns)
                    instead of forcing a 2-column grid that wastes a row. */}
                <Box
                  display="grid"
                  gridTemplateColumns={
                    isExtraSmallScreen
                      ? "repeat(1, minmax(0, 1fr))"
                      : isFiveInch
                      ? "repeat(3, minmax(0, 1fr))"
                      : isSmallScreen
                      ? "repeat(2, minmax(0, 1fr))"
                      : "repeat(3, minmax(0, 1fr))"
                  }
                  gridAutoRows={`minmax(${isExtraSmallScreen ? 44 : isFiveInch ? 48 : 52}px, auto)`}
                  gap={isFiveInch ? "6px" : "10px"}
                  flexGrow={1}
                  minHeight={0}
                >
                  <Button
                    disabled={printerActionInProgress}
                    onClick={printerConnected ? handleDisconnectPrinter : handleConnectPrinter}
                    startIcon={
                      printerConnected
                        ? <LinkOffIcon sx={{ fontSize: 13 }} />
                        : <LinkIcon sx={{ fontSize: 13 }} />
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
                    startIcon={<HomeIcon sx={{ fontSize: 14 }} />}
                    sx={{ ...utilBtnStyle, ...printerActionButtonStyle }}
                  >
                    Home All
                  </Button>
                  <Button
                    disabled={printerActionInProgress}
                    onClick={handleEmergencyStop}
                    startIcon={<StopIcon sx={{ fontSize: 14 }} />}
                    sx={{ ...eStopBtnStyle, ...printerActionButtonStyle }}
                  >
                    E-STOP
                  </Button>
                </Box>
              </Box>

              {/* Vertical separator */}
              <Box
                sx={{
                  width: isSmallScreen ? "100%" : "2px",
                  height: isSmallScreen ? "2px" : "auto",
                  backgroundColor: "#808080",
                  alignSelf: "stretch",
                  borderRadius: "2px",
                }}
              />

              {/* Right section: status cards */}
              <Box
                display="flex"
                flexDirection="column"
                gap={isFiveInch ? "6px" : "8px"}
                minHeight={0}
                sx={{ flex: isSmallScreen ? "1 1 auto" : "0 0 42%" }}
              >
                {/* Cmd + Bed Status side by side */}
                <Box display="flex" flexDirection="row" gap={isFiveInch ? "6px" : "8px"} minHeight={0}>
                  <Box sx={{ ...printerStatusCardStyle, flex: 1, minWidth: 0 }}>
                    <Box display="flex" alignItems="center" gap="4px">
                      <MyLocationIcon sx={{ fontSize: 13, color: colors.greenAccent[400] }} />
                      <Typography fontSize="11px" sx={{ color: colors.grey[300] }}>Cmd</Typography>
                    </Box>
                    <Typography fontSize={isFiveInch ? "12px" : "14px"} fontWeight="bold" sx={{ color: colors.greenAccent[400], mt: "3px" }}>
                      {printerActionStatus}
                    </Typography>
                  </Box>

                  <Box sx={{ ...printerStatusCardStyle, flex: 1, minWidth: 0 }}>
                    <Box display="flex" alignItems="center" gap="4px">
                      <ThermostatIcon sx={{ fontSize: 13, color: colors.redAccent[400] }} />
                      <Typography fontSize="11px" sx={{ color: colors.grey[300] }}>Bed Status</Typography>
                    </Box>
                    <Typography fontSize={isFiveInch ? "12px" : "14px"} fontWeight="bold" sx={{ color: colors.redAccent[300], mt: "3px" }}>
                      {bedTemperature !== null ? `${bedTemperature.toFixed(1)} °C` : "—"}
                    </Typography>
                  </Box>
                </Box>

                {/* Position spanning full width */}
                <Box sx={printerStatusCardStyle}>
                  <Box display="flex" alignItems="center" gap="4px">
                    <MyLocationIcon sx={{ fontSize: 13, color: colors.greenAccent[400] }} />
                    <Typography fontSize="11px" sx={{ color: colors.grey[300] }}>Position</Typography>
                  </Box>
                  <Typography
                    fontSize={isFiveInch ? "11px" : "14px"}
                    fontWeight="bold"
                    sx={{ color: colors.greenAccent[400], mt: "3px", wordBreak: "break-all" }}
                  >
                    X:{printerPosition.x !== null && printerPosition.x !== undefined ? Number(printerPosition.x).toFixed(1) : "—"}{" "}
                    Y:{printerPosition.y !== null && printerPosition.y !== undefined ? Number(printerPosition.y).toFixed(1) : "—"}{" "}
                    Z:{printerPosition.z !== null && printerPosition.z !== undefined ? Number(printerPosition.z).toFixed(1) : "—"}
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
            icon={<SwapHorizIcon style={{ color: "#009688", fontSize: isFiveInch ? 22 : 28 }} />}
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
            icon={<BoltIcon style={{ color: "#FF9800", fontSize: isFiveInch ? 22 : 28 }} />}
          />
        ),
      };
    }

    return box;
  });

  const updateGridColumns = () => {
    const screenWidth = window.innerWidth;
    const screenHeight = window.innerHeight;
    const isCompactPanel = screenWidth <= 1024 && screenHeight <= 700;
    const isMobile = screenWidth <= 800;
    // FIX: dedicated flag for 5-inch portrait (720 × 1280).
    // Keeps stat boxes in one row and gives content cards enough rows.
    const isFiveInchLayout = screenWidth <= 720;
    const isExtraSmall = screenWidth <= 520;

    setBoxes((prevBoxes) =>
      prevBoxes.map((box) => {
        // ── Control buttons (1, 2) and stat boxes (3, 4) ──────────────────────
        if ([1, 2].includes(box.id)) {
          return {
            ...box,
            // FIX: at 720 px use span 3 → all four top widgets fit in one row of 12 columns.
            gridColumn: isFiveInchLayout ? "span 3" : isMobile ? "span 6" : isCompactPanel ? "span 3" : "span 2",
            gridRow: "span 1",
          };
        }
        if ([3, 4].includes(box.id)) {
          return {
            ...box,
            gridColumn: isFiveInchLayout ? "span 3" : isMobile ? "span 6" : isCompactPanel ? "span 3" : "span 2",
            // FIX: keep stat boxes at span 1 on 5-inch so they sit in the same row as buttons.
            gridRow: isFiveInchLayout ? "span 1" : isMobile ? "span 2" : "span 1",
          };
        }
        // ── Charts ────────────────────────────────────────────────────────────
        if (box.id === 7 || box.id === 8) {
          return {
            ...box,
            gridColumn: "span 12",
            // FIX: span 4 rows (≈328 px at 82 px base) gives charts a good height on 5-inch.
            gridRow: isFiveInchLayout ? "span 4" : isMobile ? "span 4" : isCompactPanel ? "span 3" : "span 3",
          };
        }
        // ── Printer controls card ──────────────────────────────────────────────
        if (box.id === 9) {
          return {
            ...box,
            gridColumn: isMobile ? "span 12" : isCompactPanel ? "span 12" : "span 8",
            // FIX: span 4 (≈328 px) gives enough room for the 3-button row + status cards.
            gridRow: isFiveInchLayout ? "span 4" : isMobile ? "span 3" : "span 2",
          };
        }
        // ── Camera card ────────────────────────────────────────────────────────
        if (box.id === 10) {
          return {
            ...box,
            gridColumn: isMobile ? "span 12" : isCompactPanel ? "span 12" : "span 4",
            // FIX: span 4 keeps camera card proportional with printer card.
            gridRow: isFiveInchLayout ? "span 4" : isMobile ? "span 3" : isCompactPanel ? "span 3" : "span 2",
          };
        }
        return box;
      })
    );
  };

  useEffect(() => {
    updateGridColumns();
    window.addEventListener("resize", updateGridColumns);
    return () => {
      window.removeEventListener("resize", updateGridColumns);
    };
  }, []);

  return (
    <Box m={dashboardOuterMargin}>
      {/* HEADER — hidden on small / compact displays */}
      {showDashboardHeader && (
        <Box display="flex" justifyContent="space-between" alignItems="center">
          <Header title="DASHBOARD" subtitle="Welcome to your dashboard" />
          <Box>
            <Button
              onClick={downloadDeviceData}
              sx={{
                backgroundColor: colors.blueAccent[700],
                color: colors.grey[100],
                fontSize: "clamp(11px, 1.2vw, 14px)",
                fontWeight: "bold",
                padding: { xs: "8px 12px", sm: "10px 20px" },
                minWidth: 0,
              }}
            >
              <DownloadOutlinedIcon sx={{ mr: { xs: 0, sm: "10px" } }} />
              <Box component="span" sx={{ display: { xs: "none", sm: "inline" } }}>
                Download Reports
              </Box>
            </Button>
          </Box>
        </Box>
      )}

      {/* GRID */}
      <Box
        display="grid"
        gridTemplateColumns="repeat(12, 1fr)"
        gridAutoRows={dashboardGridAutoRows}
        gap={dashboardGridGap}
      >
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