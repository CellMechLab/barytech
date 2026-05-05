import React, { createContext, useState, useContext } from "react";

// Create SaveContext
const SaveContext = createContext();

// Custom Hook for using SaveContext
export const useSave = () => useContext(SaveContext);

// SaveContext Provider
export const SaveProvider = ({ children }) => {
  const [saveEnabled, setSaveEnabled] = useState(false);

  return (
    <SaveContext.Provider value={{ saveEnabled, setSaveEnabled }}>
      {children}
    </SaveContext.Provider>
  );
};
