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
import ControlSlider from "./ControlSlider";
import { useState, useCallback, useRef, useContext, useEffect } from "react";
import DraggableBox from "./DraggableBox"; // Import DraggableBox component
import { WebSocketContext } from "./WebSocketProvider";
import BoltIcon from "@mui/icons-material/Bolt";
import SwapHorizIcon from "@mui/icons-material/SwapHoriz";

const Dashboard = () => {
  const theme = useTheme();
  const colors = tokens(theme.palette.mode);
  const [totalDataPoints, setTotalDataPoints] = useState(0);
  const { dataBuffer } = useContext(WebSocketContext);
  const [saveEnabled, setSaveEnabled] = useState(false);

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
  // Dynamically adjust font sizes for title
  const titleFontSize = isSmallScreen
    ? "14px"
    : isMediumScreen
    ? "16px"
    : isLargeScreen
    ? "18px"
    : "20px";

  const subtitleFontSize = isSmallScreen
    ? "16px"
    : isMediumScreen
    ? "16px"
    : isLargeScreen
    ? "15px"
    : "22px";
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
    {
      id: 5,
      content: <StatBox title="Received data" subtitle="-" />,
      gridColumn: "span 2",
      gridRow: "span 1",
      lineColor: "#925DDC",
      areaColor: "#B78FEA",
      data: transformedData.series1.length,
    },
    {
      id: 6,
      content: <StatBox title="Received data" subtitle="-" />,
      gridColumn: "span 2",
      gridRow: "span 1",
      lineColor: "#925DDC",
      areaColor: "#B78FEA",
      data: transformedData.series1.length,
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
                Data Points
              </Typography>
              <Typography
                fontSize={subtitleFontSize}
                color={colors.greenAccent[500]}
              >
                number
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
      gridColumn: "span 4",
      gridRow: "span 2",
      content: (
        <Box
          p={isSmallScreen ? "15px" : "30px"} // Adjust padding for responsiveness
          sx={{
            width: "100%", // Make the box take full width on smaller screens
          }}
        >
          <Typography
            fontWeight="bold"
            sx={{ color: colors.grey[100] }}
            fontSize={titleFontSize}
            textAlign="center"
          >
            Control
          </Typography>
          <Box
            display="flex"
            flexDirection="column"
            alignItems="center"
            mt="25px"
            sx={{
              width: "100%", // Ensure inner Box adapts to smaller screens
            }}
          >
            <ControlSlider />
          </Box>
        </Box>
      ),
    },
    {
      id: 9,
      gridColumn: "span 4",
      gridRow: "span 2",
      content: (
        <Box p="15px">
          <Typography
            fontWeight="bold"
            sx={{ color: colors.grey[100] }}
            fontSize={titleFontSize}
          >
            Last Posted Data Force
          </Typography>
          <Box height="250px">{/* <BarChart isDashboard={true} /> */}</Box>
        </Box>
      ),
    },
    {
      id: 10,
      gridColumn: "span 4",
      gridRow: "span 2",
      content: (
        <Box p="15px">
          <Typography
            fontWeight="bold"
            sx={{ color: colors.grey[100] }}
            fontSize={titleFontSize}
          >
            Last Posted Data Pressure
          </Typography>
          <Box height="250px">
            {/* <GeographyChart isDashboard={true} /> */}
          </Box>
        </Box>
      ),
    },
  ]);
  const updatedBoxes = boxes.map((box) => {
    if (box.id === 3) {
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
    } else if (box.id === 5) {
      return {
        ...box,
        data: series2Data,
        content: (
          <StatBox
            title="Received points"
            subtitle={
              Array.isArray(transformedData.series1)
                ? transformedData.series1.length
                : 0
            }
          />
        ),
      };
    }
    return box;
  });

  const updateGridColumns = () => {
    const screenWidth = window.innerWidth;
    console.log("udapted", screenWidth)
    setBoxes((prevBoxes) =>
      prevBoxes.map((box) => ({
        ...box,
        gridColumn:
        screenWidth <= 800
        ? [1, 2, 3, 4, 5, 6].includes(box.id)
          ? "span 6"
          : [8, 9, 10].includes(box.id)
          ? "span 12"
          : box.gridColumn
        : [1, 2, 3, 4, 5, 6].includes(box.id)
        ? "span 2"
        : [8, 9, 10].includes(box.id)
        ? "span 4"
        : box.gridColumn,
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
    <Box m="20px">
      {/* HEADER */}
      {!isSmallScreen && (<Box display="flex" justifyContent="space-between" alignItems="center">
        <Header title="DASHBOARD" subtitle="Welcome to your dashboard" />

        <Box>
          <Button
            onClick={() => chartRef.current.downloadDataBufferAsCSV()}
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
        gridAutoRows="140px"
        gap="20px"
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
