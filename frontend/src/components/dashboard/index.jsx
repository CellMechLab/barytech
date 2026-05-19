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

  // ─── Breakpoints ────────────────────────────────────────────────────────────
  const isExtraSmallScreen  = useMediaQuery("(max-width:520px)");
  const isFiveInch          = useMediaQuery("(max-width:720px)");
  const isSmallScreen       = useMediaQuery("(max-width:800px)");
  const isMediumScreen      = useMediaQuery("(min-width:800px) and (max-width:1024px)");
  const isLargeScreen       = useMediaQuery("(min-width:1025px) and (max-width:1440px)");
  // 7-inch landscape panels (e.g. 1024x600).
  const isSevenInchDisplay  = useMediaQuery("(max-width:1024px) and (max-height:700px)");
  // reTerminal and similar wide-but-short screens (1280x720).
  // Requires width >= 1025 so it doesn't clash with isSevenInchDisplay.
  const isCompactLandscape  = useMediaQuery("(min-width:1025px) and (max-height:760px)");

  // ─── Typography ─────────────────────────────────────────────────────────────
  const titleFontSize = isSmallScreen
    ? "13px"
    : isCompactLandscape
    ? "13px"
    : isSevenInchDisplay
    ? "15px"
    : isMediumScreen
    ? "16px"
    : isLargeScreen
    ? "18px"
    : "20px";

  // ─── Layout helpers ──────────────────────────────────────────────────────────
  // Header is hidden on compact displays — every vertical pixel matters.
  const showDashboardHeader =
    !isSmallScreen && !isSevenInchDisplay && !isCompactLandscape;

  const dashboardOuterMargin = isExtraSmallScreen
    ? "6px"
    : isFiveInch
    ? "10px"
    : isCompactLandscape
    ? "8px"
    : isSevenInchDisplay
    ? "10px"
    : "20px";

  const dashboardGridGap = isExtraSmallScreen
    ? "6px"
    : isFiveInch
    ? "8px"
    : isCompactLandscape
    ? "8px"
    : isSevenInchDisplay
    ? "12px"
    : "20px";

  // reTerminal 1280x720 target layout (8px margin each side, 8px gap):
  //
  //   Row 1  — 4 stat/control boxes  : 1 row  x 70px =  70px
  //   Rows 2-4 — charts side-by-side : 3 rows x 70px = 210px + 2x8 gap = 226px  (x2 = same height)
  //   Rows 5-6 — printer + camera    : 2 rows x 70px = 140px + 1x8 gap = 148px
  //
  //   Total grid height: 70 + 8 + 226 + 8 + 148 = 460px   <- fits in 720-16=704px ✓
  //   (rows + gaps: 6 rows + 5 gaps = 6x70 + 5x8 = 460px)
  const dashboardGridAutoRows = isCompactLandscape
    ? "minmax(70px, auto)"
    : isSevenInchDisplay
    ? "minmax(118px, auto)"
    : isFiveInch
    ? "minmax(82px, auto)"
    : isSmallScreen
    ? "minmax(100px, auto)"
    : "minmax(140px, auto)";

  const [transformedData, setTransformedData] = useState({ series1: [], series2: [] });
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
        if (box.id === 3) return { ...box, data: transformedData.series1 };
        if (box.id === 4) return { ...box, data: transformedData.series2 };
        return box;
      })
    );
  }, [transformedData]);

  const chartRef = useRef();
  const handleDownload = () => {
    if (chartRef.current) chartRef.current.downloadChart();
  };
  const setChartRef = useCallback((ref) => { chartRef.current = ref; }, []);

  const handleDrop = (fromId, toId) => {
    const newBoxes = [...boxes];
    const fromBox = newBoxes.find((b) => b.id === fromId);
    const toBox   = newBoxes.find((b) => b.id === toId);
    if (!fromBox || !toBox) return;
    [fromBox.gridColumn, toBox.gridColumn] = [toBox.gridColumn, fromBox.gridColumn];
    [fromBox.gridRow,    toBox.gridRow]    = [toBox.gridRow,    fromBox.gridRow];
    setBoxes(newBoxes);
  };

  const handleHover = (fromId, toId) => {
    const newBoxes = [...boxes];
    const fi = newBoxes.findIndex((b) => b.id === fromId);
    const ti = newBoxes.findIndex((b) => b.id === toId);
    if (fi === -1 || ti === -1) return;
    [newBoxes[fi], newBoxes[ti]] = [newBoxes[ti], newBoxes[fi]];
    setBoxes(newBoxes);
  };

  const handleDelete = (id) => {
    setBoxes((prev) => prev.filter((b) => b.id !== id));
  };

  const chartHeaderMt = isCompactLandscape ? "4px"  : isExtraSmallScreen ? "6px"  : isSmallScreen ? "10px" : "18px";
  const chartHeaderPx = isCompactLandscape ? "10px" : isExtraSmallScreen ? "8px"  : isSmallScreen ? "14px" : "24px";

  const [boxes, setBoxes] = useState([
    { id: 9,  gridColumn: "span 4",  gridRow: "span 2", content: null },
    { id: 10, gridColumn: "span 8",  gridRow: "span 2", content: null },
    {
      id: 7,
      gridColumn: "span 12",
      gridRow: "span 3",
      content: (
        <Box width="100%" height="100%" display="flex" flexDirection="column" sx={{ minHeight: 0, overflow: "hidden" }}>
          <Box mt={chartHeaderMt} px={chartHeaderPx} display="flex" justifyContent="space-between" alignItems="center" sx={{ flexShrink: 0 }}>
            <Typography fontWeight="bold" sx={{ color: colors.grey[100], fontSize: "clamp(11px, 1.1vw, 20px)" }}>
              Force vs Time
            </Typography>
            <IconButton onClick={handleDownload}>
              <DownloadOutlinedIcon sx={{ fontSize: "clamp(14px, 1.4vw, 26px)", color: colors.greenAccent[500] }} />
            </IconButton>
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
          <Box mt={chartHeaderMt} px={chartHeaderPx} display="flex" justifyContent="space-between" alignItems="center" sx={{ flexShrink: 0 }}>
            <Typography fontWeight="bold" sx={{ color: colors.grey[100], fontSize: "clamp(11px, 1.1vw, 20px)" }}>
              Z vs Time
            </Typography>
            <IconButton onClick={handleDownload}>
              <DownloadOutlinedIcon sx={{ fontSize: "clamp(14px, 1.4vw, 26px)", color: colors.greenAccent[500] }} />
            </IconButton>
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
      content: <ControlButton type="save" saveEnabled={saveEnabled} setSaveEnabled={setSaveEnabled} />,
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
    // ─── Camera card (box 10) ────────────────────────────────────────────────
    if (box.id === 10) {
      // Compact landscape card: 4 cols wide (~394px), 2 rows tall (~148px).
      // Jog pad at 34px/cell: 3x34 + 2x2 = 106px — fits in ~110px available content.
      const cameraJogControlSize = isExtraSmallScreen ? 34
        : isFiveInch          ? 40
        : isSmallScreen       ? 42
        : isCompactLandscape  ? 34
        : isSevenInchDisplay  ? 44
        : 52;

      const cameraJogIconSize = isExtraSmallScreen ? 16
        : isFiveInch         ? 18
        : isSmallScreen      ? 20
        : isCompactLandscape ? 15
        : 24;

      const cameraJogBtnStyle = {
        backgroundColor: colors.greenAccent[700],
        borderRadius: "5px",
        border: `1px solid ${colors.greenAccent[500]}`,
        color: colors.grey[100],
        width:  cameraJogControlSize,
        height: cameraJogControlSize,
        "&:hover":    { backgroundColor: colors.greenAccent[600] },
        "&:disabled": { opacity: 0.35 },
      };

      const cameraStepBtnStyle = (step) => ({
        minWidth:        isCompactLandscape ? "34px" : isExtraSmallScreen ? "38px" : isFiveInch ? "42px" : "52px",
        fontSize:        isCompactLandscape ? "10px" : isExtraSmallScreen ? "11px" : isFiveInch ? "12px" : "14px",
        padding:         isCompactLandscape ? "1px 3px" : isExtraSmallScreen ? "2px 4px" : isFiveInch ? "4px 8px" : "6px 10px",
        backgroundColor: jogStep === step ? colors.greenAccent[700] : "transparent",
        color:           colors.grey[100],
        border:          `1px solid ${colors.greenAccent[500]}`,
        "&:hover":       { backgroundColor: colors.greenAccent[600] },
      });

      const cardPad  = isCompactLandscape ? "7px"  : isExtraSmallScreen ? "6px"  : isFiveInch ? "10px" : "12px";
      const cardGap  = isCompactLandscape ? "4px"  : isFiveInch ? "6px" : "8px";
      const jogGap   = isCompactLandscape ? "2px"  : "3px";

      return {
        ...box,
        content: (
          <Box width="100%" p={cardPad} height="100%" display="flex" flexDirection="column" gap={cardGap} sx={{ overflow: "hidden", boxSizing: "border-box" }}>
            <Typography fontWeight="bold" sx={{ color: colors.grey[100] }} fontSize={titleFontSize}>
              Camera View
            </Typography>

            {/* Always row layout on landscape (compact or full) */}
            <Box display="flex" flexDirection="row" flexGrow={1} minHeight={0} sx={{ overflow: "hidden" }}>

              {/* Controls column */}
              <Box display="flex" flexDirection="column" gap={cardGap} sx={{ flex: "0 0 auto", minWidth: 0, overflow: "hidden", pr: "6px" }}>
                {/* Step selector */}
                <Box display="flex" alignItems="center" gap="3px" flexWrap="wrap">
                  <Typography fontSize="9px" sx={{ color: colors.grey[400] }}>Step:</Typography>
                  {[0.1, 1, 10].map((step) => (
                    <Button key={step} size="small" sx={cameraStepBtnStyle(step)} onClick={() => setJogStep(step)}>
                      {step}
                    </Button>
                  ))}
                  <Typography fontSize="9px" sx={{ color: colors.grey[400] }}>mm</Typography>
                </Box>

                {/* XY + Z jog pads */}
                <Box display="flex" gap="5px" alignItems="flex-start">
                  {/* Head XY */}
                  <Box display="flex" flexDirection="column" alignItems="center" gap="2px">
                    <Typography fontSize="9px" sx={{ color: colors.grey[400] }}>XY</Typography>
                    <Box
                      display="grid"
                      gridTemplateColumns={`repeat(3, ${cameraJogControlSize}px)`}
                      gridTemplateRows={`repeat(3, ${cameraJogControlSize}px)`}
                      gap={jogGap}
                    >
                      <Box />
                      <IconButton size="small" disabled={printerActionInProgress} onClick={() => handleJogAxis("Y", 1)} sx={cameraJogBtnStyle}>
                        <ArrowUpwardIcon sx={{ fontSize: cameraJogIconSize }} />
                      </IconButton>
                      <Box />
                      <IconButton size="small" disabled={printerActionInProgress} onClick={() => handleJogAxis("X", -1)} sx={cameraJogBtnStyle}>
                        <ArrowBackIcon sx={{ fontSize: cameraJogIconSize }} />
                      </IconButton>
                      <Box display="flex" alignItems="center" justifyContent="center" sx={{ backgroundColor: colors.primary[400], borderRadius: "5px" }}>
                        <Typography fontSize="8px" sx={{ color: colors.grey[400] }}>XY</Typography>
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
                  <Box display="flex" flexDirection="column" alignItems="center" gap="2px">
                    <Typography fontSize="9px" sx={{ color: colors.grey[400] }}>Z</Typography>
                    <Box display="flex" flexDirection="column" alignItems="center" gap={jogGap}>
                      <IconButton size="small" disabled={printerActionInProgress} onClick={() => handleJogAxis("Z", -1)} sx={cameraJogBtnStyle}>
                        <ArrowUpwardIcon sx={{ fontSize: cameraJogIconSize }} />
                      </IconButton>
                      <Box display="flex" alignItems="center" justifyContent="center" sx={{ width: cameraJogControlSize, height: cameraJogControlSize, backgroundColor: colors.primary[400], borderRadius: "5px" }}>
                        <Typography fontSize="8px" sx={{ color: colors.grey[400] }}>Z</Typography>
                      </Box>
                      <IconButton size="small" disabled={printerActionInProgress} onClick={() => handleJogAxis("Z", 1)} sx={cameraJogBtnStyle}>
                        <ArrowDownwardIcon sx={{ fontSize: cameraJogIconSize }} />
                      </IconButton>
                    </Box>
                  </Box>
                </Box>
              </Box>

              {/* Divider */}
              <Box sx={{ width: "2px", alignSelf: "stretch", backgroundColor: "#808080", borderRadius: "2px", flexShrink: 0 }} />

              {/* Live feed */}
              <Box display="flex" flexDirection="column" gap="2px" sx={{ flex: "1 1 0", minWidth: 0, pl: "6px" }}>
                <Typography fontSize="9px" sx={{ color: colors.grey[400] }}>Live feed</Typography>
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
    }

    // ─── Printer controls card (box 9) ──────────────────────────────────────
    if (box.id === 9) {
      // Compact landscape: card is now 4 cols (~394px) x 2 rows (~148px).
      // Buttons need to be compact — 32px fits title + 3 buttons + status tiles.
      const btnMinH    = isCompactLandscape ? 30  : isExtraSmallScreen ? 44 : isFiveInch ? 48 : isSmallScreen ? 52 : 64;
      const btnFont    = isCompactLandscape ? "10px" : isExtraSmallScreen ? "11px" : isFiveInch ? "12px" : "13px";
      const btnPad     = isCompactLandscape ? "2px 4px"  : isExtraSmallScreen ? "4px 6px" : isFiveInch ? "8px 10px" : "10px 12px";
      const cardPad    = isCompactLandscape ? "5px"  : isFiveInch ? "10px" : "12px";
      const innerGap   = isCompactLandscape ? "3px"  : isFiveInch ? "6px" : "8px";
      const sectionPad = isCompactLandscape ? "4px"  : "10px";

      const utilBtnBase = {
        fontSize: btnFont, padding: btnPad,
        color: colors.grey[100],
        border: `1px solid ${colors.greenAccent[500]}`,
        backgroundColor: colors.greenAccent[800] ?? colors.greenAccent[700],
        "&:hover": { backgroundColor: colors.greenAccent[600] },
        "&:disabled": { opacity: 0.35 },
        minWidth: 0, minHeight: btnMinH,
      };
      const eStopBase = {
        fontSize: btnFont, padding: btnPad,
        color: "#fff", border: "1px solid #c62828", backgroundColor: "#c62828",
        "&:hover": { backgroundColor: "#b71c1c" },
        minWidth: 0, minHeight: btnMinH,
      };
      const connectBase = {
        ...utilBtnBase,
        backgroundColor: printerConnected ? colors.greenAccent[700] : "transparent",
      };
      const disconnectBase = {
        fontSize: btnFont, padding: btnPad,
        color: colors.grey[100], border: "1px solid #c62828", backgroundColor: "transparent",
        "&:hover": { backgroundColor: "#c62828" },
        "&:disabled": { opacity: 0.35 },
        minWidth: 0, minHeight: btnMinH,
      };
      const fullWidth = { width: "100%", minHeight: btnMinH };

      const panelStyle = {
        backgroundColor: colors.primary[400],
        borderRadius: "8px",
        minHeight: 0,
        boxSizing: "border-box",
      };
      const statusCardStyle = {
        ...panelStyle,
        display: "flex", flexDirection: "column", justifyContent: "center",
        flex: 1, p: isCompactLandscape ? "4px 6px" : "10px 12px",
      };
      const statusFontSize  = isCompactLandscape ? "10px" : "14px";
      const statusIconSize  = isCompactLandscape ? 10 : 14;
      const labelFontSize   = isCompactLandscape ? "9px" : "12px";

      return {
        ...box,
        content: (
          <Box p={cardPad} display="flex" flexDirection="column" gap={innerGap} height="100%" width="100%" minHeight={0} sx={{ overflow: "hidden", boxSizing: "border-box" }}>
            <Typography fontWeight="bold" sx={{ color: colors.grey[100] }} fontSize={titleFontSize}>
              Printer Controls & Status
            </Typography>

            {/* Always row layout on landscape */}
            <Box display="flex" flexDirection="row" gap={isCompactLandscape ? "8px" : "12px"} flexGrow={1} minHeight={0}>

              {/* Left: 3 action buttons */}
              <Box
                display="flex" flexDirection="column" gap={isCompactLandscape ? "3px" : "10px"}
                minHeight={0}
                sx={{ ...panelStyle, flex: isCompactLandscape ? "0 0 52%" : "0 0 58%", overflow: "hidden", p: sectionPad }}
              >
                {/* Always 3 columns on landscape — all three buttons in one row */}
                <Box
                  display="grid"
                  gridTemplateColumns="repeat(3, minmax(0, 1fr))"
                  gridAutoRows={`minmax(${btnMinH}px, auto)`}
                  gap={isCompactLandscape ? "6px" : "10px"}
                  flexGrow={1}
                  minHeight={0}
                >
                  <Button
                    disabled={printerActionInProgress}
                    onClick={printerConnected ? handleDisconnectPrinter : handleConnectPrinter}
                    startIcon={printerConnected ? <LinkOffIcon sx={{ fontSize: 12 }} /> : <LinkIcon sx={{ fontSize: 12 }} />}
                    sx={{ ...(printerConnected ? disconnectBase : connectBase), ...fullWidth }}
                  >
                    {printerConnected ? "Disconnect" : "Connect"}
                  </Button>
                  <Button
                    disabled={printerActionInProgress}
                    onClick={handleHomePrinter}
                    startIcon={<HomeIcon sx={{ fontSize: 12 }} />}
                    sx={{ ...utilBtnBase, ...fullWidth }}
                  >
                    Home All
                  </Button>
                  <Button
                    disabled={printerActionInProgress}
                    onClick={handleEmergencyStop}
                    startIcon={<StopIcon sx={{ fontSize: 12 }} />}
                    sx={{ ...eStopBase, ...fullWidth }}
                  >
                    E-STOP
                  </Button>
                </Box>
              </Box>

              {/* Vertical separator */}
              <Box sx={{ width: "2px", alignSelf: "stretch", backgroundColor: "#808080", borderRadius: "2px" }} />

              {/* Right: status tiles */}
              <Box display="flex" flexDirection="column" gap={isCompactLandscape ? "3px" : "8px"} minHeight={0} sx={{ flex: isCompactLandscape ? "0 0 44%" : "0 0 42%" }}>
                <Box display="flex" flexDirection="row" gap={isCompactLandscape ? "3px" : "8px"} minHeight={0}>
                  <Box sx={{ ...statusCardStyle, flex: 1, minWidth: 0 }}>
                    <Box display="flex" alignItems="center" gap="3px">
                      <MyLocationIcon sx={{ fontSize: statusIconSize, color: colors.greenAccent[400] }} />
                      <Typography fontSize={labelFontSize} sx={{ color: colors.grey[300] }}>Cmd</Typography>
                    </Box>
                    <Typography fontSize={statusFontSize} fontWeight="bold" sx={{ color: colors.greenAccent[400], mt: "2px" }}>
                      {printerActionStatus}
                    </Typography>
                  </Box>
                  <Box sx={{ ...statusCardStyle, flex: 1, minWidth: 0 }}>
                    <Box display="flex" alignItems="center" gap="3px">
                      <ThermostatIcon sx={{ fontSize: statusIconSize, color: colors.redAccent[400] }} />
                      <Typography fontSize={labelFontSize} sx={{ color: colors.grey[300] }}>Bed</Typography>
                    </Box>
                    <Typography fontSize={statusFontSize} fontWeight="bold" sx={{ color: colors.redAccent[300], mt: "2px" }}>
                      {bedTemperature !== null ? `${bedTemperature.toFixed(1)} °C` : "—"}
                    </Typography>
                  </Box>
                </Box>
                <Box sx={statusCardStyle}>
                  <Box display="flex" alignItems="center" gap="3px">
                    <MyLocationIcon sx={{ fontSize: statusIconSize, color: colors.greenAccent[400] }} />
                    <Typography fontSize={labelFontSize} sx={{ color: colors.grey[300] }}>Position</Typography>
                  </Box>
                  <Typography fontSize={isCompactLandscape ? "10px" : "14px"} fontWeight="bold" sx={{ color: colors.greenAccent[400], mt: "2px" }}>
                    X:{printerPosition.x != null ? Number(printerPosition.x).toFixed(1) : "—"}{" "}
                    Y:{printerPosition.y != null ? Number(printerPosition.y).toFixed(1) : "—"}{" "}
                    Z:{printerPosition.z != null ? Number(printerPosition.z).toFixed(1) : "—"}
                  </Typography>
                </Box>
              </Box>
            </Box>
          </Box>
        ),
      };
    }

    if (box.id === 3) {
      return {
        ...box,
        data: series1Data,
        content: (
          <StatBox
            title="Displacement"
            subtitle={`${series1Data?.[series1Data.length - 1]?.value?.toFixed(2) ?? "-"} cm`}
            icon={<SwapHorizIcon style={{ color: "#009688", fontSize: isCompactLandscape ? 18 : 28 }} />}
          />
        ),
      };
    }
    if (box.id === 4) {
      return {
        ...box,
        data: series2Data,
        content: (
          <StatBox
            title="Force"
            subtitle={`${series2Data?.[series2Data.length - 1]?.value?.toFixed(2) ?? "-"} cm`}
            icon={<BoltIcon style={{ color: "#FF9800", fontSize: isCompactLandscape ? 18 : 28 }} />}
          />
        ),
      };
    }

    return box;
  });

  // ─── Grid column/row assignments ─────────────────────────────────────────────
  const updateGridColumns = () => {
    const sw = window.innerWidth;
    const sh = window.innerHeight;

    // reTerminal 1280x720 landscape
    const isCompactLandscapeLayout = sw >= 1025 && sh <= 760;
    // Smaller 7-inch landscape panels
    const isCompactPanel            = sw <= 1024 && sh <= 700;
    const isMobile                  = sw <= 800;
    const isFiveInchLayout          = sw <= 720;
    const isExtraSmall              = sw <= 520;

    setBoxes((prev) => prev.map((box) => {
      // ── Stat + control widgets (1, 2, 3, 4) ───────────────────────────────
      if ([1, 2, 3, 4].includes(box.id)) {
        return {
          ...box,
          // All four in one row across all landscape + compact layouts
          gridColumn: isCompactLandscapeLayout ? "span 3"
                    : isFiveInchLayout         ? "span 3"
                    : isMobile                 ? "span 6"
                    : isCompactPanel           ? "span 3"
                    :                           "span 2",
          gridRow: isMobile && !isFiveInchLayout && [3, 4].includes(box.id)
            ? "span 2"
            : "span 1",
        };
      }

      // ── Charts (7, 8) ──────────────────────────────────────────────────────
      if (box.id === 7 || box.id === 8) {
        return {
          ...box,
          // KEY: side-by-side on compact landscape → two charts each ~620px wide
          gridColumn: isCompactLandscapeLayout ? "span 6" : "span 12",
          gridRow:    isCompactLandscapeLayout ? "span 3"
                    : isFiveInchLayout         ? "span 4"
                    : isMobile                 ? "span 4"
                    : isCompactPanel           ? "span 3"
                    :                           "span 3",
        };
      }

      // ── Printer controls (9) ────────────────────────────────────────────────
      if (box.id === 9) {
        return {
          ...box,
          // Compact landscape: narrower card (span 4) — controls are secondary to camera
          gridColumn: isCompactLandscapeLayout ? "span 4"
                    : isMobile                 ? "span 12"
                    : isCompactPanel           ? "span 12"
                    :                           "span 8",
          gridRow:    isCompactLandscapeLayout ? "span 2"
                    : isFiveInchLayout         ? "span 4"
                    : isMobile                 ? "span 3"
                    :                           "span 2",
        };
      }

      // ── Camera (10) ─────────────────────────────────────────────────────────
      if (box.id === 10) {
        return {
          ...box,
          // Compact landscape: larger card (span 8) — camera feed is primary
          gridColumn: isCompactLandscapeLayout ? "span 8"
                    : isMobile                 ? "span 12"
                    : isCompactPanel           ? "span 12"
                    :                           "span 4",
          gridRow:    isCompactLandscapeLayout ? "span 2"
                    : isFiveInchLayout         ? "span 4"
                    : isMobile                 ? "span 3"
                    : isCompactPanel           ? "span 3"
                    :                           "span 2",
        };
      }

      return box;
    }));
  };

  useEffect(() => {
    updateGridColumns();
    window.addEventListener("resize", updateGridColumns);
    return () => window.removeEventListener("resize", updateGridColumns);
  }, []);

  return (
    <Box m={dashboardOuterMargin}>
      {showDashboardHeader && (
        <Box display="flex" justifyContent="space-between" alignItems="center" mb="12px">
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