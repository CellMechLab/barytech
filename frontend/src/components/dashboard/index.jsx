// Dashboard page for live monitoring, charting, and printer controls.
import {
  Box,
  Button,
  CircularProgress,
  IconButton,
  Typography,
  Tooltip,
  useTheme,
  useMediaQuery,
} from "@mui/material";
import { tokens } from "../../theme";
import DownloadOutlinedIcon from "@mui/icons-material/DownloadOutlined";
import Header from "./Header";
import LineChart from "./LineChart";
import StatBox from "./StatBox";
import ControlButton from "./ControlButton";
import FolderSelector from "./FolderSelector";
import { useState, useCallback, useRef, useContext, useEffect, useMemo } from "react";
import DraggableBox from "./DraggableBox";
import { WebSocketContext } from "./WebSocketProvider";
import usePrinterControls from "./hooks/usePrinterControls";
import { useSave } from "../../context/SaveContext";
import ExportFolderModal from "../ExportFolderModal";
import { BACKEND_BASE_URL, VIDEO_BASE_URL } from "../../config/endpoints";
import { toast } from "sonner";
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
const FORCE_UNIT = process.env.REACT_APP_FORCE_UNIT || "N";
const Dashboard = () => {
  const backendApiUrl = BACKEND_BASE_URL;
  const theme = useTheme();
  const colors = tokens(theme.palette.mode);
  const [totalDataPoints, setTotalDataPoints] = useState(0);
  // Pulls data stream, WS toggle, live connection state, and socket from shared context.
  const { dataBuffer, toggleConnection, connected, socket } = useContext(WebSocketContext);
  // Shared save state: flag + the folder that incoming data will be written into.
  const { saveEnabled, setSaveEnabled, activeFolderId } = useSave();

  // Folder list fetched on mount so the download button can show the active folder name.
  const [folders, setFolders] = useState([]);
  // True while HDF5 export is in progress inside the metadata modal.
  const [folderExporting, setFolderExporting] = useState(false);
  // Controls visibility of the export metadata confirmation modal.
  const [exportModalOpen, setExportModalOpen] = useState(false);

  // Fetch folders once on mount using the same auth pattern as FolderSelector.
  useEffect(() => {
    const loadFolders = async () => {
      try {
        const token = sessionStorage.getItem("authToken");
        if (!token) return;
        const res = await fetch(`${BACKEND_BASE_URL}/api/folders/`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) setFolders(await res.json());
      } catch (err) {
        // Non-critical — button will fall back to generic label if fetch fails.
        console.error("[Dashboard] folder fetch failed:", err);
      }
    };
    loadFolders();
  }, []);

  // Derives a display label from the folders list for the download button.
  const activeFolderName = activeFolderId
    ? (folders.find((f) => f.id === activeFolderId)?.name ?? "folder")
    : null;

  const {
    printerActionInProgress,
    printerActionStatus,
    printerPosition,
    bedTemperature,
    hotendTemperature,
    indentationStatus,
    jogStep,
    setJogStep,
    printerConnected,
    handleJogAxis,
    handleHomePrinter,
    handleEmergencyStop,
    handleExtrude,
    handleRetract,
    handleStartIndentation,
    handleConnectPrinter,
    handleDisconnectPrinter,
  } = usePrinterControls(backendApiUrl);


  /**
   * Unified connect/disconnect handler for the Controls & Status card.
   * Toggles both the backend data WebSocket and the printer serial connection
   * so a single button drives the full connection lifecycle.
   */
  const handleCombinedConnectionToggle = async () => {
    if (connected) {
      // Close the backend data WebSocket first, then release the printer serial port.
      toggleConnection();
      await handleDisconnectPrinter();
    } else {
      // Open the backend data WebSocket first, then open the printer serial port.
      toggleConnection();
      await handleConnectPrinter();
    }
  };

  /**
   * Starts save mode and immediately triggers an indentation test.
   * Save is stopped automatically when the test completes or fails,
   * so each indentation run is recorded as exactly one curve.
   * Requires an open WS socket and a selected folder.
   */
  const handleStartIndentationWithSave = () => {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      // Prevent silent failure when the data socket is not ready.
      toast.error("Connect first before starting indentation.", {
        style: { backgroundColor: "red", color: "white" },
      });
      return;
    }
    if (!activeFolderId) {
      // Save destination must be chosen before recording can begin.
      toast.error("Select a folder before starting indentation.", {
        style: { backgroundColor: "red", color: "white" },
      });
      return;
    }
    // Enable save so incoming data is persisted from the first measurement.
    setSaveEnabled(true);
    // Notify backend: open a new curve in the selected folder.
    socket.send(JSON.stringify({ type: "save", save: true, folder_id: activeFolderId }));
    toast("Recording started — indentation test beginning.", {
      style: { backgroundColor: "#3da58a", color: "white" },
    });
    // Mark that this save session was auto-started so the completion handler can stop it.
    indentationSaveActive.current = true;
    handleStartIndentation();
  };

  // Auto-stop save when the indentation test finishes or fails so the curve is closed cleanly.
  useEffect(() => {
    if (!indentationSaveActive.current) return;

    // Detect both normal completion and request failure so no orphaned open-save exists.
    const completed = indentationStatus === "Indentation completed. Ready for the next test.";
    const failed    = indentationStatus === "Unable to start indentation. Check the printer connection and try again.";

    if (completed || failed) {
      if (socket && socket.readyState === WebSocket.OPEN) {
        setSaveEnabled(false);
        // Instruct backend to close and persist the current curve.
        socket.send(JSON.stringify({ type: "save", save: false, folder_id: activeFolderId }));
        toast(
          completed ? "Indentation complete — curve saved." : "Indentation failed — recording stopped.",
          { style: { backgroundColor: completed ? "#3da58a" : "#d32f2f", color: "white" } }
        );
      }
      indentationSaveActive.current = false;
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [indentationStatus]);

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
  // iPad landscape (1180x820, and neighboring iPad landscape sizes like 1194x834).
  // Wider than a 7-inch panel, taller than reTerminal (>760px), so it needs its own tier
  // rather than falling through to the desktop/large-screen layout and overflowing.
  const isIpadLandscape     = useMediaQuery("(min-width:1080px) and (max-width:1300px) and (min-height:761px) and (max-height:900px)");

  // ─── Typography ─────────────────────────────────────────────────────────────
  const titleFontSize = isSmallScreen
    ? "13px"
    : isCompactLandscape
    ? "13px"
    : isSevenInchDisplay
    ? "15px"
    : isIpadLandscape
    ? "16px"
    : isMediumScreen
    ? "16px"
    : isLargeScreen
    ? "18px"
    : "20px";

  // ─── Layout helpers ──────────────────────────────────────────────────────────
  // Header is hidden only on small/mobile screens; compact landscape (1280×720) shows a condensed header row.
  const showDashboardHeader =
    !isSmallScreen && !isSevenInchDisplay;

  const dashboardOuterMargin = isExtraSmallScreen
    ? "6px"
    : isFiveInch
    ? "10px"
    : isCompactLandscape
    ? "8px"
    : isSevenInchDisplay
    ? "10px"
    : isIpadLandscape
    ? "12px"
    : "20px";

  const dashboardGridGap = isExtraSmallScreen
    ? "6px"
    : isFiveInch
    ? "8px"
    : isCompactLandscape
    ? "8px"
    : isSevenInchDisplay
    ? "12px"
    : isIpadLandscape
    ? "10px"
    : "20px";

  // reTerminal 1280x720 target layout (8px margin each side, 8px gap):
  //
  //   Row 1  — 4 stat/control boxes  : 1 row  x 70px =  70px
  //   Rows 2-4 — charts side-by-side : 3 rows x 70px = 210px + 2x8 gap = 226px  (x2 = same height)
  //   Rows 5-6 — printer + camera    : 2 rows x 70px = 140px + 1x8 gap = 148px
  //
  //   Total grid height: 70 + 8 + 226 + 8 + 148 = 460px   <- fits in 720-16=704px ✓
  //   (rows + gaps: 6 rows + 5 gaps = 6x70 + 5x8 = 460px)
  // iPad landscape 1180x820 target layout (12px margin each side, 10px gap):
  //
  //   Charts side-by-side : 4 rows x 112px = 448px + 3x10 gap =  478px
  //   Printer + camera    : 2 rows x 112px = 224px + 1x10 gap =  234px
  //
  //   Total grid height: 478 + 10 (row gap between chart block and control block) + 234 = 722px
  //   Plus ~24px margin (12 top + 12 bottom) + ~50px header = 796px  <- fits in 820px ✓
  const dashboardGridAutoRows = isCompactLandscape
    ? "minmax(70px, auto)"
    : isSevenInchDisplay
    ? "minmax(118px, auto)"
    : isIpadLandscape
    ? "minmax(112px, auto)"
    : isFiveInch
    ? "minmax(82px, auto)"
    : isSmallScreen
    ? "minmax(100px, auto)"
    : "minmax(140px, auto)";

  // Controls whether the Camera View card shows manual jog controls or automatic mode.
  // Defaults to automatic so the indentation workflow is immediately available on load.
  const [cameraMode, setCameraMode] = useState("auto");

  const dashboardData = useMemo(() => {
    let displacementTotal = 0;
    let displacementCount = 0;
    let forceTotal = 0;
    let forceCount = 0;

    dataBuffer.forEach((item) => {
      const displacement = Number(item.displacement);
      const force = Number(item.force);

      if (item.displacement != null && Number.isFinite(displacement)) {
        displacementTotal += displacement;
        displacementCount += 1;
      }

      if (item.force != null && Number.isFinite(force)) {
        forceTotal += force;
        forceCount += 1;
      }
    });

    const recentData = dataBuffer;
    const toChartDate = (item, index) => {
      const timestamp = item.timestamp_ms ?? item.timestamp ?? item.time ?? item.t;
      const numericTimestamp = Number(timestamp);
      const date = Number.isFinite(numericTimestamp)
        ? new Date(Math.abs(numericTimestamp) > 1e12 ? numericTimestamp : numericTimestamp * 1000)
        : new Date(timestamp);

      return Number.isFinite(date.getTime()) ? date : new Date(index);
    };

    return {
      displacementAvg:
        displacementCount > 0 ? displacementTotal / displacementCount : null,
      forceAvg: forceCount > 0 ? forceTotal / forceCount : null,
      displacementSeries: recentData.flatMap((item, index) => {
        const value = Number(item.displacement);
        return item.displacement != null && Number.isFinite(value)
          ? [{ date: toChartDate(item, index), value }]
          : [];
      }),
      forceSeries: recentData.flatMap((item, index) => {
        const value = Number(item.force);
        return item.force != null && Number.isFinite(value)
          ? [{ date: toChartDate(item, index), value }]
          : [];
      }),
    };
  }, [dataBuffer]);

  const chartRef = useRef();
  // True while save was auto-started by an indentation test; drives the auto-stop effect.
  const indentationSaveActive = useRef(false);
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

  const chartHeaderMt = isCompactLandscape ? "4px"  : isExtraSmallScreen ? "6px"  : isSmallScreen ? "10px" : isIpadLandscape ? "6px" : "18px";
  const chartHeaderPx = isCompactLandscape ? "10px" : isExtraSmallScreen ? "8px"  : isSmallScreen ? "14px" : isIpadLandscape ? "16px" : "24px";

  const [boxes, setBoxes] = useState([
    { id: 9,  gridColumn: "span 7",  gridRow: "span 2", content: null },
    { id: 10, gridColumn: "span 5",  gridRow: "span 2", content: null },
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
    // {
    //   id: 3,
    //   content: (
    //     <StatBox
    //       measurementColor="#006666"
    //       title="Displacement Avg"
    //       subtitle="— cm"
    //     />
    //   ),
    //   gridColumn: "span 6",
    //   gridRow: "span 1",
    //   lineColor: "#009688",
    //   areaColor: "rgba(0,150,136,0.2)",
    //   data: [],
    // },
    // {
    //   id: 4,
    //   content: (
    //     <StatBox
    //       measurementColor="#D35400"
    //       title="Force Avg"
    //       subtitle={`— ${FORCE_UNIT}`}
    //     />
    //   ),
    //   gridColumn: "span 6",
    //   gridRow: "span 1",
    //   lineColor: "#FF9800",
    //   areaColor: "rgba(255,152,0,0.2)",
    //   data: [],
    // },
  ]);

  const updatedBoxes = boxes.map((box) => {
    // ─── Camera card (box 10) ────────────────────────────────────────────────
    if (box.id === 10) {
      // Compact landscape card: 5 cols wide (~490px), 2 rows tall (~148px).
      // Jog pad at 34px/cell: 3x34 + 2x2 = 106px — fits in available content height.
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

      // Shared tab button style — active tab gets a solid green fill.
      const tabBtnStyle = (mode) => ({
        fontSize:        isCompactLandscape ? "9px" : "11px",
        padding:         isCompactLandscape ? "1px 6px" : "2px 10px",
        minWidth:        0,
        color:           colors.grey[100],
        border:          `1px solid ${colors.greenAccent[500]}`,
        borderRadius:    "4px",
        backgroundColor: cameraMode === mode ? colors.greenAccent[700] : "transparent",
        "&:hover":       { backgroundColor: colors.greenAccent[600] },
        textTransform:   "none",
      });

      // Style for the Start Indentation button in automatic mode.
      const startIndentBtnStyle = {
        fontSize:        isCompactLandscape ? "11px" : "13px",
        padding:         isCompactLandscape ? "6px 10px" : "10px 16px",
        color:           colors.grey[100],
        border:          `1px solid ${colors.blueAccent[400]}`,
        backgroundColor: colors.blueAccent[700],
        borderRadius:    "6px",
        "&:hover":       { backgroundColor: colors.blueAccent[600] },
        "&:disabled":    { opacity: 0.35 },
        textTransform:   "none",
        minWidth:        0,
      };

      return {
        ...box,
        content: (
          <Box width="100%" p={cardPad} height="100%" display="flex" flexDirection="column" gap={cardGap} sx={{ overflow: "hidden", boxSizing: "border-box" }}>
            {/* Header row: title + mode tabs */}
            <Box display="flex" alignItems="center" justifyContent="space-between" sx={{ flexShrink: 0 }}>
              <Typography fontWeight="bold" sx={{ color: colors.grey[100] }} fontSize={titleFontSize}>
                Camera View
              </Typography>
              {/* Manual / Automatic tab toggle */}
              <Box display="flex" gap="4px">
                <Button size="small" sx={tabBtnStyle("manual")} onClick={() => setCameraMode("manual")}>
                  Manual
                </Button>
                <Button size="small" sx={tabBtnStyle("auto")} onClick={() => setCameraMode("auto")}>
                  Automatic
                </Button>
              </Box>
            </Box>

            {/* Always row layout on landscape (compact or full) */}
            <Box display="flex" flexDirection="row" flexGrow={1} minHeight={0} sx={{ overflow: "hidden" }}>

              {/* Controls column — content switches based on active mode */}
              <Box display="flex" flexDirection="column" gap={cardGap} sx={{ flex: "0 0 auto", minWidth: 0, overflow: "hidden", pr: "6px" }}>

                {cameraMode === "manual" ? (
                  <>
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
                  </>
                ) : (
                  /* Automatic mode — Start Indentation now also owns save start/stop */
                  <Box display="flex" flexDirection="column" alignItems="center" justifyContent="center" flexGrow={1} gap="8px">
                    <Typography fontSize="9px" sx={{ color: colors.grey[400], textAlign: "center" }}>
                      Automatic indentation test
                    </Typography>
                    {/* Tooltip appears when no folder is selected so the user knows why the button is disabled.
                        The outer span is required because MUI Tooltip needs mouse events the disabled button suppresses. */}
                    <Tooltip title={!activeFolderId ? "Select a folder first" : ""} placement="top">
                      <Box component="span">
                        <Button
                          disabled={printerActionInProgress || !activeFolderId}
                          onClick={handleStartIndentationWithSave}
                          sx={{
                            ...startIndentBtnStyle,
                            // Show green fill while a recording session is active.
                            ...(saveEnabled && {
                              backgroundColor: colors.greenAccent[700],
                              border: `1px solid ${colors.greenAccent[400]}`,
                            }),
                          }}
                        >
                          {saveEnabled ? "⏺ Recording…" : "▶ Start Indentation"}
                        </Button>
                      </Box>
                    </Tooltip>
                    {/* Live indentation test state (Waiting / In progress / Completed / Failed) */}
                    <Typography fontSize="9px" sx={{ color: colors.greenAccent[400], textAlign: "center" }}>
                      {indentationStatus}
                    </Typography>
                  </Box>
                )}
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
      // Compact landscape: card is 7 cols (~726px) x 2 rows (~148px).
      // Reduced button height/font/padding to free up space now that the card is narrower.
      const btnMinH    = isCompactLandscape ? 32  : isExtraSmallScreen ? 44 : isFiveInch ? 48 : isSmallScreen ? 52 : 64;
      const btnFont    = isCompactLandscape ? "10px" : isExtraSmallScreen ? "11px" : isFiveInch ? "12px" : "13px";
      const btnPad     = isCompactLandscape ? "2px 6px"  : isExtraSmallScreen ? "4px 6px" : isFiveInch ? "8px 10px" : "10px 12px";
      const cardPad    = isCompactLandscape ? "6px"  : isFiveInch ? "10px" : "12px";
      const innerGap   = isCompactLandscape ? "4px"  : isFiveInch ? "6px" : "8px";
      const sectionPad = isCompactLandscape ? "5px"  : "10px";

      const utilBtnBase = {
        fontSize: btnFont, padding: btnPad,
        color: colors.grey[100],
        border: `1px solid ${colors.greenAccent[500]}`,
        backgroundColor: colors.greenAccent[800] ?? colors.greenAccent[700],
        "&:hover": { backgroundColor: colors.greenAccent[600] },
        "&:disabled": { opacity: 0.35 },
        minWidth: 0, minHeight: btnMinH,
      };
      const connectBase = {
        ...utilBtnBase,
        backgroundColor: connected ? colors.greenAccent[700] : "transparent",
      };
      const disconnectBase = {
        fontSize: btnFont, padding: btnPad,
        color: colors.grey[100], border: "1px solid #c62828", backgroundColor: "transparent",
        "&:hover": { backgroundColor: "#c62828" },
        "&:disabled": { opacity: 0.35 },
        minWidth: 0, minHeight: btnMinH,
      };
      // Ensures every action button stretches to fill its grid cell.
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
        flex: 1, p: isCompactLandscape ? "5px 8px" : "10px 12px",
      };
      const statusFontSize  = isCompactLandscape ? "10px" : "14px";
      const statusIconSize  = isCompactLandscape ? 11 : 14;
      const labelFontSize   = isCompactLandscape ? "9px" : "12px";

      return {
        ...box,
        content: (
          <Box p={cardPad} display="flex" flexDirection="column" gap={innerGap} height="100%" width="100%" minHeight={0} sx={{ overflow: "hidden", boxSizing: "border-box" }}>
            <Typography fontWeight="bold" sx={{ color: colors.grey[100] }} fontSize={titleFontSize}>
              Controls & Status
            </Typography>

            {/* Always row layout on landscape */}
            <Box display="flex" flexDirection="row" gap={isCompactLandscape ? "8px" : "12px"} flexGrow={1} minHeight={0}>

              {/* Left: 3 action buttons */}
              <Box
                display="flex" flexDirection="column" gap={isCompactLandscape ? "3px" : "10px"}
                minHeight={0}
                sx={{ ...panelStyle, flex: "0 0 58%", overflow: "hidden", p: sectionPad }}
              >
                {/* Folder selector — must be set before Save can be pressed */}
                <FolderSelector fontSize={isCompactLandscape ? "10px" : "11px"} />
                {/* 3 columns: Connect · Home · E-Stop (Save is now driven by Start Indentation) */}
                <Box
                  display="grid"
                  gridTemplateColumns="repeat(3, minmax(0, 1fr))"
                  gridAutoRows={`minmax(${btnMinH}px, auto)`}
                  gap={isCompactLandscape ? "5px" : "8px"}
                  flexGrow={1}
                  minHeight={0}
                >
                  <Button
                    disabled={printerActionInProgress}
                    onClick={handleCombinedConnectionToggle}
                    startIcon={connected ? <LinkOffIcon sx={{ fontSize: 11 }} /> : <LinkIcon sx={{ fontSize: 11 }} />}
                    sx={{ ...(connected ? disconnectBase : connectBase), ...fullWidth }}
                  >
                    {connected ? "Disconnect" : "Connect"}
                  </Button>
                  <Button
                    disabled={printerActionInProgress}
                    onClick={handleHomePrinter}
                    startIcon={<HomeIcon sx={{ fontSize: 11 }} />}
                    sx={{ ...utilBtnBase, ...fullWidth }}
                  >
                    Home All
                  </Button>
                  {/* Tooltip explains why the button is disabled when no folder is selected. */}
                  <Tooltip title={!activeFolderId ? "Select a folder first" : ""} placement="top">
                    <Box
                      component="span"
                      sx={{ display: "flex", width: "100%", minHeight: btnMinH, height: "100%", alignSelf: "stretch" }}
                    >
                      <Button
                        disabled={!activeFolderId || folderExporting}
                        onClick={() => setExportModalOpen(true)}
                        startIcon={
                          folderExporting
                            ? <CircularProgress size={11} sx={{ color: colors.grey[100] }} />
                            : <DownloadOutlinedIcon sx={{ fontSize: 11 }} />
                        }
                        sx={{ ...utilBtnBase, ...fullWidth, flex: 1, height: "100%" }}
                      >
                        {folderExporting ? "Exporting…" : (activeFolderName ?? "Download")}
                      </Button>
                    </Box>
                  </Tooltip>
                </Box>
              </Box>

              {/* Vertical separator */}
              <Box sx={{ width: "2px", alignSelf: "stretch", backgroundColor: "#808080", borderRadius: "2px" }} />

              {/* Right: status tiles */}
              <Box display="flex" flexDirection="column" gap={isCompactLandscape ? "3px" : "8px"} minHeight={0} sx={{ flex: "0 0 42%" }}>
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

    // if (box.id === 3) {
    //   // Computes the mean of all displacement values currently in the buffer.
    //   return {
    //     ...box,
    //     data: dashboardData.displacementSeries,
    //     content: (
    //       <StatBox
    //         title="Displacement Avg"
    //         subtitle={dashboardData.displacementAvg !== null ? `${dashboardData.displacementAvg.toFixed(2)} cm` : "—"}
    //         icon={<SwapHorizIcon style={{ color: "#009688", fontSize: isCompactLandscape ? 18 : 28 }} />}
    //       />
    //     ),
    //   };
    // }
    // if (box.id === 4) {
    //   // Computes the mean of all force values currently in the buffer.
    //   return {
    //     ...box,
    //     data: dashboardData.forceSeries,
    //     content: (
    //       <StatBox
    //         title="Force Avg"
    //         subtitle={dashboardData.forceAvg !== null ? `${dashboardData.forceAvg.toFixed(2)} ${FORCE_UNIT}` : "—"}
    //         icon={<BoltIcon style={{ color: "#FF9800", fontSize: isCompactLandscape ? 18 : 28 }} />}
    //       />
    //     ),
    //   };
    // }

    return box;
  });

  // ─── Grid column/row assignments ─────────────────────────────────────────────
  const updateGridColumns = () => {
    const sw = window.innerWidth;
    const sh = window.innerHeight;

    // reTerminal 1280x720 landscape
    const isCompactLandscapeLayout = sw >= 1025 && sh <= 760;
    // iPad landscape (1180x820 and similar iPad landscape sizes): wide enough for
    // side-by-side charts like reTerminal, but taller — falls outside isCompactLandscapeLayout
    // (sh > 760) so it needs its own check or it would fall through to the full-desktop
    // stacked-chart layout and overflow the 820px viewport.
    const isIpadLandscapeLayout     = sw >= 1080 && sw <= 1300 && sh >= 761 && sh <= 900;
    // Smaller 7-inch landscape panels
    const isCompactPanel            = sw <= 1024 && sh <= 700;
    const isMobile                  = sw <= 800;
    const isFiveInchLayout          = sw <= 720;
    const isExtraSmall              = sw <= 520;

    setBoxes((prev) => prev.map((box) => {
      // ── Stat + control widgets (1, 2, 3, 4) ───────────────────────────────
      // Boxes 1 and 2 merged into box 9 — only stat boxes 3 and 4 remain in the top row.
      // Two boxes fill 12 columns: each spans 6 on all layouts, full-width on small mobile.
      // if ([3, 4].includes(box.id)) {
      //   return {
      //     ...box,
      //     gridColumn: isMobile ? "span 12" : "span 6",
      //     gridRow: isMobile ? "span 2" : "span 1",
      //   };
      // }

      // ── Charts (7, 8) ──────────────────────────────────────────────────────
      if (box.id === 7 || box.id === 8) {
        return {
          ...box,
          // KEY: side-by-side on compact landscape / iPad landscape → two charts sharing a row
          gridColumn: (isCompactLandscapeLayout || isIpadLandscapeLayout) ? "span 6" : "span 12",
          gridRow:    isCompactLandscapeLayout ? "span 3"
                    : isIpadLandscapeLayout    ? "span 4"
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
          // Compact landscape / iPad landscape: narrowed to span 7 to give Camera View more room.
          gridColumn: (isCompactLandscapeLayout || isIpadLandscapeLayout) ? "span 7"
                    : isMobile                 ? "span 12"
                    : isCompactPanel           ? "span 12"
                    :                           "span 8",
          gridRow:    (isCompactLandscapeLayout || isIpadLandscapeLayout) ? "span 2"
                    : isFiveInchLayout         ? "span 4"
                    : isMobile                 ? "span 3"
                    :                           "span 2",
        };
      }

      // ── Camera (10) ─────────────────────────────────────────────────────────
      if (box.id === 10) {
        return {
          ...box,
          // Compact landscape / iPad landscape: widened to span 5 for a larger live-feed area.
          gridColumn: (isCompactLandscapeLayout || isIpadLandscapeLayout) ? "span 5"
                    : isMobile                 ? "span 12"
                    : isCompactPanel           ? "span 12"
                    :                           "span 4",
          gridRow:    (isCompactLandscapeLayout || isIpadLandscapeLayout) ? "span 2"
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
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={isCompactLandscape ? "5px" : isIpadLandscape ? "8px" : "12px"}>
          <Header title="DASHBOARD" subtitle="Welcome to your dashboard" />
          {/* Emergency stop in the header — always visible for quick access. */}
          <Button
            onClick={handleEmergencyStop}
            startIcon={<StopIcon sx={{ color: "#fff" }} />}
            sx={{
              fontSize: "clamp(11px, 1.1vw, 14px)",
              padding: "10px 12px",
              fontWeight: 600,
              textTransform: "none",
              whiteSpace: "nowrap",
              minWidth: 0,
              color: "#fff",
              border: "1px solid #c62828",
              backgroundColor: "#c62828",
              "&:hover": { backgroundColor: "#b71c1c" },
            }}
          >
            E-STOP
          </Button>
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

      <ExportFolderModal
        open={exportModalOpen}
        onClose={() => setExportModalOpen(false)}
        folderId={activeFolderId}
        folderName={activeFolderName}
        colors={colors}
        onExportingChange={setFolderExporting}
      />
    </Box>
  );
};

export default Dashboard;