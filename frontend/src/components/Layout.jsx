// src/components/Layout.js

import React, { useState } from "react";
import { useLocation, Outlet } from "react-router-dom";
import { CssBaseline } from "@mui/material";
import Sidebar from "./global/Sidebar";
import Topbar from "./global/Topbar";
import RightSideBar from "./global/RightSideBar";

const Layout = () => {
  const location = useLocation();
  const [isSideBar, setIsSideBar] = useState(true);

  // Determine if we are on the auth route
  const hideLayout = location.pathname === "/auth";

  return (
    <div className="app">
      {!hideLayout && <Sidebar isSidebar={isSideBar} />}
      {!hideLayout && <RightSideBar isSideBar={isSideBar} setIsSideBar={setIsSideBar} />}

      <main className="content">
        {!hideLayout && <Topbar />}
        <Outlet context={{ setIsSideBar }}/>
      </main>
    </div>
  );
};

export default Layout;
