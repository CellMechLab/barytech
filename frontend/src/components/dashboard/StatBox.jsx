import { Box, Typography, useTheme, useMediaQuery } from "@mui/material";
import { tokens } from "../../theme";

const StatBox = ({ title, subtitle, icon, measurementColor, increase }) => {
  const theme = useTheme();
  const colors = tokens(theme.palette.mode);

  // Define custom breakpoints
  const isSmallScreen = useMediaQuery('(max-width:768px)');
  const isMediumScreen = useMediaQuery('(min-width:769px) and (max-width:1024px)');
  const isLargeScreen = useMediaQuery('(min-width:1025px) and (max-width:1440px)');
  const isExtraLargeScreen = useMediaQuery('(min-width:1441px)');
  
  // Dynamically adjust card height based on screen size
  const dynamicHeight = isSmallScreen
    ? "200px"
    : isMediumScreen
    ? "300px"
    : isLargeScreen
    ? "350px"
    : "400px"; // This will apply for extra large screens
  
  // Dynamically adjust font size for subtitles
  const subtitleFontSize = isSmallScreen
    ? "16px"
    : isMediumScreen
    ? "16px"
    : isLargeScreen
    ? "15px"
    : "22px";
  
  // Dynamically adjust font sizes for title
  const titleFontSize = isSmallScreen
    ? "14px"
    : isMediumScreen
    ? "16px"
    : isLargeScreen
    ? "18px"
    : "20px";
  
  return (
    <Box
      width="100%"
      display="flex"
      flexDirection="column"
      justifyContent="space-between"
      height={dynamicHeight} // Apply dynamic height
    >
      {/* Top Section */}
      <Box>
        <Box
          display="flex"
          justifyContent="space-between"
          alignItems="center"
          borderBottom="1px solid lightgrey"
          colors={colors.grey[100]}
          paddingLeft="10px"
          paddingTop="8px"
        >
          <Box>
            <Typography
              fontWeight="bold"
              sx={{ color: colors.grey[100] }}
              fontSize={titleFontSize} // Apply dynamic font size for title
            >
              {title}
            </Typography>
          </Box>
        </Box>
        <Box display="flex" pl="10px" pt="8px">
          {icon && <Box mt="8px">{icon}</Box>}
          <Typography
            ml="14px"
            sx={{ color: "#111" }}
            fontSize={subtitleFontSize} // Apply dynamic font size
          >
            {subtitle}
          </Typography>
        </Box>
      </Box>
    </Box>
  );
};

export default StatBox;
