import React, { useContext, useState } from "react";
import {
  Box,
  IconButton,
  useTheme,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Menu,
  MenuItem,
  Typography,
  FormControl,
  Select,
  InputLabel,
} from "@mui/material";
import LightModeOutlinedIcon from "@mui/icons-material/LightModeOutlined";
import DarkModeOutlinedIcon from "@mui/icons-material/DarkModeOutlined";
import NotificationsOutlinedIcon from "@mui/icons-material/NotificationsOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import PersonOutlinedIcon from "@mui/icons-material/PersonOutlined";
import CircleIcon from "@mui/icons-material/Circle";
import RefreshIcon from "@mui/icons-material/Refresh";
import { useNavigate } from "react-router-dom";
import { useUser } from "../../context/UserContext";
import { WebSocketContext } from "../dashboard/WebSocketProvider";
import { ColorModeContext, tokens } from "../../theme";
import DownloadIcon from "@mui/icons-material/Download";
import { useSave } from "../../context/SaveContext"; // Import the custom hook

const Topbar = () => {
  const theme = useTheme();
  const colors = tokens(theme.palette.mode);
  const colorMode = useContext(ColorModeContext);
  const navigate = useNavigate();
  const { user, logout } = useUser();
  const { connected } = useContext(WebSocketContext);
  const [modalOpen, setModalOpen] = useState(false);
  const [anchorEl, setAnchorEl] = useState(null);
  const [interval, setInterval] = useState("1 min");

  const handleNavigate = () => {
    if (user) {
      setModalOpen(true);
    } else {
      navigate("/auth");
    }
  };
  const { saveEnabled } = useSave();
  const handleCloseModal = () => {
    setModalOpen(false);
  };

  const handleOpenMenu = (event) => {
    setAnchorEl(event.currentTarget);
  };

  const handleCloseMenu = () => {
    setAnchorEl(null);
  };

  const handleLogout = () => {
    sessionStorage.removeItem("authToken");
    logout(navigate);
    handleCloseMenu();
  };

  const handleIntervalChange = (event) => {
    setInterval(event.target.value);
  };

  const UserInfoModal = ({ user, onClose }) => (
    <Dialog open={!!user} onClose={onClose}>
      <DialogTitle>User Info</DialogTitle>
      <DialogContent>
        <p>Username: {user?.username}</p>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} color="primary">
          Close
        </Button>
      </DialogActions>
    </Dialog>
  );

  return (
    <Box
      display="flex"
      justifyContent="space-between"
      alignItems="center"
      borderRadius="8px"
      p={1} // Decreased padding to reduce height
      backgroundColor={colors.primary[400]}
      sx={{
        width: "95%", // Keep it centered with 95% width
        margin: "10px auto", // Adjust top margin
      }}
    >
      {/* COMPANY NAME */}
      <Typography
        variant="h5"
        color={colors.grey[100]}
        sx={{ display: "flex", alignItems: "center", fontWeight: "bold" }}
      >
        SCHAEFER SRL
      </Typography>

      {/* SEARCH BAR & STATUS ICONS */}
      <Box
        display="flex"
        alignItems="center"
        justifyContent="flex-end" // Align everything to the right
        borderRadius="3px"
        sx={{ width: "50%", padding: "0" }} // Reduce padding
      >
        {/* <FormControl
          size="small"
          sx={{ minWidth: 100, mr: 1, color: colors.grey[100] }}
        > */}
          {/* <InputLabel
            id="refresh-interval-label"
            sx={{ color: colors.grey[100] }}
          >
            Interval
          </InputLabel>
          <Select
            labelId="refresh-interval-label"
            id="refresh-interval-select"
            value={interval}
            onChange={handleIntervalChange}
            label="Interval"
            sx={{ color: colors.grey[100] }}
          >
            <MenuItem value="0 min">No interval</MenuItem>
            <MenuItem value="1 min">1 min</MenuItem>
            <MenuItem value="5 min">5 min</MenuItem>
            <MenuItem value="30 min">30 min</MenuItem>
          </Select>
        </FormControl> */}

          {/* <IconButton type="button" sx={{ p: 1, mr: 1 }}>
            <RefreshIcon />
          </IconButton> */}

        <Box display="flex" alignItems="center">
          <CircleIcon
            fontSize="small"
            sx={{
              color: connected
                ? colors.greenAccent[200]
                : colors.redAccent[500],
              mr: 1,
            }}
          />
          {/* <Typography variant="body2" color={colors.grey[100]}>
            Auto Refresh is On
          </Typography> */}
        </Box>
        <Box
          sx={{
            width: "40px", // Reserve space for the icon
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            visibility: saveEnabled ? "visible" : "hidden", // Hide or show the icon
          }}
        >
        {saveEnabled && (
          <IconButton sx={{ p: 1, ml: 1 }}>
            <DownloadIcon sx={{ color: colors.grey[100] }} />
          </IconButton>
        )}
      </Box>
      </Box>

      {/* ICONS */}
      <Box display="flex" alignItems="center">
        <IconButton onClick={colorMode.toggleColorMode}>
          {theme.palette.mode === "dark" ? (
            <DarkModeOutlinedIcon />
          ) : (
            <LightModeOutlinedIcon />
          )}
        </IconButton>
        <IconButton>
          <NotificationsOutlinedIcon />
        </IconButton>
        <IconButton onClick={handleOpenMenu}>
          <SettingsOutlinedIcon />
        </IconButton>
        <Menu
          anchorEl={anchorEl}
          open={Boolean(anchorEl)}
          onClose={handleCloseMenu}
        >
          <MenuItem onClick={handleLogout}>Logout</MenuItem>
        </Menu>
        <IconButton onClick={handleNavigate}>
          <PersonOutlinedIcon />
        </IconButton>
      </Box>

      {/* User Info Modal */}
      {modalOpen && <UserInfoModal user={user} onClose={handleCloseModal} />}
    </Box>
  );
};

export default Topbar;
