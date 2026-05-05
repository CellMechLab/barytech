import React, { useState } from "react";
import { Box } from "@mui/material";
// import { useDrag, useDrop } from "react-dnd";
// import { Edit, Delete, DragIndicator } from "@mui/icons-material"; // Import DragIndicator
// import { opacity } from "html2canvas/dist/types/css/property-descriptors/opacity";
import { useOutletContext } from "react-router-dom";
import LineChartWithArea from "./LineChartWithArea";

const DraggableBox = ({
  id,
  children,
  backgroundColor,
  gridColumn,
  gridRow,
  lineColor,
  areaColor,
  data
}) => {
  // DnD functionality is intentionally disabled.
  // const [{ isDragging }, drag] = useDrag({
  //   type: ItemTypes.BOX,
  //   item: { id, gridColumn, gridRow },
  //   collect: (monitor) => ({
  //     isDragging: !!monitor.isDragging(),
  //   }),
  // });
  // const [, drop] = useDrop({
  //   accept: ItemTypes.BOX,
  //   hover: (item) => {
  //     if (item.id !== id) {
  //       onHover(item.id, id); // Call onHover to update positions while hovering
  //     }
  //   },
  //   drop: (item) => {
  //     if (item.id !== id) {
  //       onDrop(item.id, id); // Finalize the drop
  //     }
  //   },
  // });

  // State to control hover visibility
  const [isHovered, setIsHovered] = useState(false);
  const { setIsSideBar } = useOutletContext(); // Get setIsSidebar from Layout
  void setIsSideBar;
  const flexStyles =
  id === 3 || id === 4
    ? {} // Do not apply center alignment
    : {
        alignItems: "center",
        justifyContent: "center",
      };
  return (
    <Box
      gridColumn={gridColumn}
      gridRow={gridRow}
      backgroundColor={backgroundColor}
      display="flex"
      flexDirection="column"
      {...flexStyles} // Spread conditionally applied styles
      style={{
        cursor: "default",
        boxShadow: isHovered
          ? "0px 4px 8px rgba(0, 0, 0, 0.2)"
          : "0px 2px 4px rgba(0, 0, 0, 0.1)",
        // ? "rgba(0, 0, 0, 0.1) 0px 0px 20px 3px"
        // : "rgba(0, 0, 0, 0.1) 0px 0px 20px 3px",
        borderRadius: "15px",
      }}
      position="relative"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Container for the hover icons */}
      {/* <Box
        sx={{
          position: "absolute",
          top: 2,
          right: 9,
          display: "flex",
          flexDirection: "row",
          transform: isHovered ? "translateY(0)" : "translateY(-10px)", // Slide down on hover
          opacity: isHovered ? 1 : 0, // Fade in on hover
          transition: "transform 0.3s ease, opacity 0.3s ease", // Transition for smooth effect
        }}
      > */}
        {/* <Box
          ref={drag} // Drag functionality only attached to this section
          sx={{
            width: "100%",
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            padding: "4px",
            cursor: "move",
            // backgroundColor: "rgba(0, 0, 0, 0.05)",
            borderTopLeftRadius: "15px",
            borderTopRightRadius: "15px",
          }}
        >
          <DragIndicator fontSize="small" /> */}
        {/* </Box> */}
        {/* <IconButton size="small" sx={{ color: "grey" }} color="inherit">
          <DragIndicator fontSize="small" />
        </IconButton> */}
        {/* <IconButton onClick={handleSidebarToggle} size="small" sx={{ color: "grey" }} color="primary">
          <Edit fontSize="small" />
        </IconButton>
        <IconButton
          size="small"
          sx={{ color: "grey" }}
          onClick={() => handleDelete(id)}
          color="error"
        >
          <Delete fontSize="small" />
        </IconButton> */}
      {/* </Box> */}

      {children}
      {id === 4 || id === 3 ? (
        <Box width="100%" height="35%">
          <LineChartWithArea lineColor={lineColor} areaColor={areaColor} data={data} />
        </Box>
      ) : null}

    </Box>
  );
};

export default DraggableBox;
