// src/context/UserContext.js
// Manages global authentication state and provides session restore on app startup.

import React, { createContext, useContext, useState, useEffect } from "react";
import { buildBackendUrl } from "../config/endpoints";

// Create the UserContext
const UserContext = createContext();

// Create a provider component
export const UserProvider = ({ children }) => {
  // Holds the currently authenticated user object, or null when logged out
  const [user, setUser] = useState(null);

  // Tracks whether the initial session restore check is still in progress.
  // Prevents ProtectedRoute from redirecting before we know if the token is valid.
  const [isAuthLoading, setIsAuthLoading] = useState(true);

  // On mount, attempt to restore the session from a token stored in sessionStorage.
  // This ensures a page refresh does not log the user out.
  useEffect(() => {
    const restoreSession = async () => {
      const token = sessionStorage.getItem("authToken");

      if (!token) {
        // No token present — nothing to restore
        setIsAuthLoading(false);
        return;
      }

      try {
        const response = await fetch(buildBackendUrl("/me"), {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (response.ok) {
          const userData = await response.json();
          // Token is valid — rehydrate user state
          setUser({ username: userData.username, user_id: userData.user_id });
        } else {
          // Token is invalid or expired — clear it so login page is shown cleanly
          sessionStorage.removeItem("authToken");
        }
      } catch (error) {
        // Prevent crash if the backend is temporarily unreachable during restore
        console.error("Session restore failed:", error);
        sessionStorage.removeItem("authToken");
      } finally {
        setIsAuthLoading(false);
      }
    };

    restoreSession();
  }, []);

  const login = (userData) => {
    setUser(userData); // Store user data on login
  };

  const logout = (navigate) => {
    setUser(null); // Clear user data
    sessionStorage.removeItem("authToken"); // Clear token
    navigate("/auth"); // Redirect to auth page
  };

  return (
    <UserContext.Provider value={{ user, login, logout, isAuthLoading }}>
      {children}
    </UserContext.Provider>
  );
};

// Custom hook to use the UserContext
export const useUser = () => {
  return useContext(UserContext);
};
