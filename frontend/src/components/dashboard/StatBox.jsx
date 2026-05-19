import { Box, Typography, useTheme } from "@mui/material";
import { tokens } from "../../theme";

const StatBox = ({ title, subtitle, icon, measurementColor, increase }) => {
  const theme = useTheme();
  const colors = tokens(theme.palette.mode);

  return (
    <Box
      width="100%"
      height="65%"
      display="flex"
      flexDirection="column"
      justifyContent="flex-start"
      sx={{ overflow: "hidden" }}
    >
      {/* Title row */}
      <Box
        display="flex"
        justifyContent="space-between"
        alignItems="center"
        borderBottom="1px solid lightgrey"
        paddingLeft="10px"
        paddingTop="6px"
        paddingBottom="6px"
        sx={{ flexShrink: 0 }}
      >
        <Typography
          fontWeight="bold"
          sx={{
            color: colors.grey[100],
            fontSize: "clamp(12px, 1.4vw, 20px)",
            lineHeight: 1.2,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {title}
        </Typography>
      </Box>

      {/* Value + icon row */}
      <Box
        display="flex"
        alignItems="center"
        pl="10px"
        pt="6px"
        gap="8px"
        sx={{ flexShrink: 0 }}
      >
        {icon && (
          <Box
            display="flex"
            alignItems="center"
            sx={{ flexShrink: 0, "& svg": { fontSize: "clamp(18px, 2vw, 28px)" } }}
          >
            {icon}
          </Box>
        )}
        <Typography
          sx={{
            color: measurementColor || colors.greenAccent[500],
            fontSize: "clamp(13px, 1.5vw, 22px)",
            fontWeight: 600,
            lineHeight: 1.3,
            wordBreak: "break-all",
          }}
        >
          {subtitle}
        </Typography>
      </Box>
    </Box>
  );
};

export default StatBox;