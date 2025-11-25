// src/App.js

import React, { useState } from "react";
import { BrowserRouter as Router, Route, Routes } from "react-router-dom";
import { DndProvider } from "react-dnd";
import { HTML5Backend } from "react-dnd-html5-backend";
import { WebSocketProvider } from "./components/dashboard/WebSocketProvider";
import { ColorModeContext, useMode } from "./theme";
import { CssBaseline, ThemeProvider } from "@mui/material";
import Dashboard from "./components/dashboard/index";
import AuthPage from "./components/auth/AuthPage";
import Layout from "./components/Layout"; // Import Layout
import { UserProvider } from "./context/UserContext"; // Import UserProvider
import ProtectedRoute from "./components/routes/ProtectedRoute"; // Import ProtectedRoute
import Devices from "./components/devices/index";
import DeviceData from "./components/deviceData/index";
import AddDevice from "./components/form/index";
import AdminPanel from "./components/admin/AdminPanel"; // Import AdminPanel
import { SaveProvider } from "./context/SaveContext";

const App = () => {
  const [theme, colorMode] = useMode();

  return (
    <UserProvider>
      <ColorModeContext.Provider value={colorMode}>
        <ThemeProvider theme={theme}>
          <CssBaseline />
          <Router>
            <WebSocketProvider>
              <SaveProvider>
                <DndProvider backend={HTML5Backend}>
                  <Routes>
                    {/* Route without Layout */}
                    <Route path="/auth" element={<AuthPage />} />

                    {/* Protected Route with Layout */}
                    <Route
                      path="/"
                      element={
                        <ProtectedRoute>
                          <Layout />
                        </ProtectedRoute>
                      }
                    >
                      {/* Dashboard Route inside Layout */}
                      <Route index element={<Dashboard />} />
                      <Route path="/devices" element={<Devices />} />
                      <Route path="/device-data" element={<DeviceData />} />
                      <Route path="/add-device" element={<AddDevice />} />
                      <Route path="/admin" element={<AdminPanel />} />
                    </Route>
                  </Routes>
                </DndProvider>
              </SaveProvider>
            </WebSocketProvider>
          </Router>
        </ThemeProvider>
      </ColorModeContext.Provider>
    </UserProvider>
  );
};

export default App;
