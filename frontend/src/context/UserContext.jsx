// src/context/UserContext.js

import React, { createContext, useContext, useState } from "react";

// Create the UserContext
const UserContext = createContext();

// Create a provider component
export const UserProvider = ({ children }) => {
  const [user, setUser] = useState(null);

  const login = (userData) => {
    setUser(userData); // Store user data on login
    // sessionStorage.setItem("authToken", userData.token); // Save token to sessionStorage
  };

  const logout = (navigate) => {
    setUser(null); // Clear user data
    sessionStorage.removeItem("authToken"); // Clear token
    navigate("/auth"); // Redirect to auth page
  };
  return (
    <UserContext.Provider value={{ user, login, logout }}>
      {children}
    </UserContext.Provider>
  );
};

// Custom hook to use the UserContext
export const useUser = () => {
  return useContext(UserContext);
};
