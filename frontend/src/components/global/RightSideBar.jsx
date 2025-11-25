import { useState } from "react";
import { ProSidebar, Menu, MenuItem } from "react-pro-sidebar";
import { Box, IconButton, Typography, useTheme } from "@mui/material";
import "react-pro-sidebar/dist/css/styles.css";
import { tokens } from "../../theme";
import CloseIcon from "@mui/icons-material/Close"; // Correct icon import
import PersonOutlinedIcon from "@mui/icons-material/PersonOutlined";
import HomeOutlinedIcon from "@mui/icons-material/HomeOutlined";

const Item = ({ title, icon, selected, setSelected }) => {
  const theme = useTheme();
  const colors = tokens(theme.palette.mode);
  
  return (
    <MenuItem
      active={selected === title}
      style={{
        color: colors.grey[100],
      }}
      onClick={() => setSelected(title)}
      icon={icon}
    >
      <Typography>{title}</Typography>
    </MenuItem>
  );
};

const RightSideBar = ({isSideBar, setIsSideBar}) => {
  const theme = useTheme();
  const colors = tokens(theme.palette.mode);
//   const [isSideBar, setisSideBar] = useState(false);
  const [selected, setSelected] = useState("Dashboard");

  return (
    <Box
      sx={{
        "& .pro-sidebar-inner": {
          background: `${colors.primary[400]} !important`,
          width: isSideBar ? "0px" : "350px", // Adjust the width based on collapse state
        //   transition: "width 0.3s ease", // Smooth transition for width change
        },
        "& .pro-icon-wrapper": {
          backgroundColor: "transparent !important",
        },
        "& .pro-inner-item": {
          padding: "5px 35px 5px 20px !important",
        },
        "& .pro-inner-item:hover": {
          color: "#868dfb !important",
        },
        "& .pro-menu-item.active": {
          color: "#6870fa !important",
        },
        position: "fixed", // To keep the sidebar fixed
        top: 0,
        right: 0,
        zIndex: isSideBar ? -1000 : 1000,
        height: "100%",
        width: "350px",
      }}
    >
      <ProSidebar collapsed={isSideBar} breakPoint="md">
        <Menu iconShape="square">
          {/* LOGO AND MENU ICON */}
          <MenuItem
            onClick={() => setIsSideBar(!isSideBar)}
            icon={isSideBar ? <CloseIcon /> : undefined}
            style={{
              margin: "10px 0 20px 0",
              color: colors.grey[100],
            }}
          >
            {!isSideBar && (
              <Box
                display="flex"
                justifyContent="space-between"
                alignItems="center"
                ml="15px"
              >
                <Typography variant="h3" color={colors.grey[100]}>
                  EDIT
                </Typography>
                <IconButton onClick={() => setIsSideBar(!isSideBar)}>
                  <CloseIcon />
                </IconButton>
              </Box>
            )}
          </MenuItem>

          {/* Profile Section */}
          {!isSideBar && (
            <Box mb="25px">
              <Box display="flex" justifyContent="center" alignItems="center">
                {/* <img
                  alt="profile-user"
                  width="100px"
                  height="100px"
                  src={`https://thumbs.dreamstime.com/b/admin-user-icon-account-has-virtually-unlimited-access-to-all-programs-isolated-background-vector-illustration-322126763.jpg`}
                  style={{ cursor: "pointer", borderRadius: "50%" }}
                /> */}
              </Box>
              <Box textAlign="center">
                {/* <Typography
                  variant="h2"
                  color={colors.grey[100]}
                  fontWeight="bold"
                  sx={{ m: "10px 0 0 0" }}
                >
                  Ed Roh
                </Typography>
                <Typography variant="h5" color={colors.greenAccent[500]}>
                  VP Fancy Admin
                </Typography> */}
              </Box>
            </Box>
          )}

          {/* Menu Items */}
          <Box paddingLeft={isSideBar ? undefined : "10%"}>
            {/* <Item
              title="Dashboard"
              icon={<HomeOutlinedIcon />}
              selected={selected}
              setSelected={setSelected}
            />
            <Item
              title="Profile"
              icon={<PersonOutlinedIcon />}
              selected={selected}
              setSelected={setSelected}
            /> */}
          </Box>
        </Menu>
      </ProSidebar>
    </Box>
  );
};

export default RightSideBar;
