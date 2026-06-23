import React, { createContext, useState, useContext } from "react";

// Create SaveContext
const SaveContext = createContext();

// Custom Hook for using SaveContext
export const useSave = () => useContext(SaveContext);

// SaveContext Provider
export const SaveProvider = ({ children }) => {
  // True while the backend is actively persisting incoming device data.
  const [saveEnabled, setSaveEnabled] = useState(false);
  // ID of the folder currently selected as the recording target; null = no folder chosen.
  const [activeFolderId, setActiveFolderId] = useState(null);

  return (
    <SaveContext.Provider value={{ saveEnabled, setSaveEnabled, activeFolderId, setActiveFolderId }}>
      {children}
    </SaveContext.Provider>
  );
};
