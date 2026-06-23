// Compact folder picker placed near the Save button in the Controls & Status card.
// Lets the user choose an existing folder or create a new one from a minimal dialog.
// The selected folder id is persisted in SaveContext so ControlButton and the dashboard
// save handler both send the same folder_id in every save WebSocket message.
import React, { useState, useEffect, useCallback } from "react";
import {
  Box,
  Select,
  MenuItem,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Button,
  Typography,
  Chip,
  CircularProgress,
  Tooltip,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import { useTheme } from "@mui/material/styles";
import { tokens } from "../../theme";
import { BACKEND_BASE_URL } from "../../config/endpoints";
import { useSave } from "../../context/SaveContext";

// Props:
//   fontSize — CSS font-size string propagated to text inside the component.
const FolderSelector = ({ fontSize = "11px" }) => {
  const theme = useTheme();
  // Colour palette resolved from the current light/dark theme mode.
  const colors = tokens(theme.palette.mode);

  // Shared active-folder state consumed by both the save button and the WS message.
  const { activeFolderId, setActiveFolderId } = useSave();

  // Folders fetched from GET /api/folders/ for the logged-in user.
  const [folders, setFolders] = useState([]);
  // True while the initial or refresh fetch is in flight.
  const [loading, setLoading] = useState(false);
  // Controls visibility of the "New Folder" creation dialog.
  const [dialogOpen, setDialogOpen] = useState(false);
  // Name typed by the user inside the new-folder dialog.
  const [newFolderName, setNewFolderName] = useState("");
  // True while the POST /folders/ request is in flight to disable the Create button.
  const [creating, setCreating] = useState(false);

  // Fetches the folder list for the authenticated user; called on mount and after creation.
  const fetchFolders = useCallback(async () => {
    setLoading(true);
    try {
      // Reads the JWT stored at login so the endpoint scopes data to this user.
      const token = sessionStorage.getItem("authToken");
      const res = await fetch(`${BACKEND_BASE_URL}/api/folders/`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`Folder fetch failed (${res.status})`);
      const data = await res.json();
      setFolders(data);
    } catch (err) {
      // Surface the error to the console rather than crashing the card.
      console.error("[FolderSelector] failed to fetch folders:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFolders();
  }, [fetchFolders]);

  // POSTs a new folder and immediately selects it as the active recording target.
  const handleCreateFolder = async () => {
    if (!newFolderName.trim()) return;
    setCreating(true);
    try {
      const token = sessionStorage.getItem("authToken");
      const res = await fetch(`${BACKEND_BASE_URL}/api/folders/`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ name: newFolderName.trim() }),
      });
      if (!res.ok) throw new Error(`Folder creation failed (${res.status})`);
      const created = await res.json();
      // Prepend the new folder so it appears at the top of the list.
      setFolders((prev) => [created, ...prev]);
      // Auto-select the freshly created folder so the user can immediately save.
      setActiveFolderId(created.id);
      setDialogOpen(false);
      setNewFolderName("");
    } catch (err) {
      console.error("[FolderSelector] failed to create folder:", err);
      alert("Failed to create folder. Please try again.");
    } finally {
      setCreating(false);
    }
  };

  // Closing the dialog without saving should also clear the name field.
  const handleCloseDialog = () => {
    setDialogOpen(false);
    setNewFolderName("");
  };

  // The currently selected folder object (used to render the Select value).
  const selectedFolder = folders.find((f) => f.id === activeFolderId);

  return (
    <>
      <Box display="flex" alignItems="center" gap="4px" sx={{ minWidth: 0 }}>
        {/* Label */}
        <Typography fontSize={fontSize} sx={{ color: colors.grey[400], flexShrink: 0 }}>
          Folder:
        </Typography>

        {/* Folder dropdown */}
        {loading ? (
          <CircularProgress size={12} sx={{ color: colors.greenAccent[400] }} />
        ) : (
          <Select
            value={activeFolderId ?? ""}
            onChange={(e) => setActiveFolderId(e.target.value || null)}
            displayEmpty
            size="small"
            sx={{
              fontSize,
              color: colors.grey[100],
              flex: 1,
              minWidth: 0,
              maxWidth: "200px",
              height: "24px",
              ".MuiOutlinedInput-notchedOutline": { borderColor: colors.greenAccent[700] },
              "&:hover .MuiOutlinedInput-notchedOutline": { borderColor: colors.greenAccent[500] },
              ".MuiSvgIcon-root": { color: colors.grey[300], fontSize: "14px" },
            }}
            MenuProps={{
              PaperProps: {
                sx: {
                  maxHeight: 240,
                  backgroundColor: colors.primary[400],
                },
              },
            }}
            renderValue={() =>
              selectedFolder ? (
                <Box display="flex" alignItems="center" gap="4px" sx={{ overflow: "hidden" }}>
                  <Typography fontSize={fontSize} noWrap sx={{ color: colors.grey[100] }}>
                    {selectedFolder.name}
                  </Typography>
                  {selectedFolder.curve_count > 0 && (
                    <Chip
                      label={selectedFolder.curve_count}
                      size="small"
                      sx={{
                        height: "14px",
                        fontSize: "9px",
                        backgroundColor: colors.blueAccent[700],
                        color: colors.grey[100],
                        flexShrink: 0,
                      }}
                    />
                  )}
                </Box>
              ) : (
                <Typography fontSize={fontSize} sx={{ color: colors.grey[500] }}>
                  — select —
                </Typography>
              )
            }
          >
            {/* Explicit none option so the user can deselect */}
            <MenuItem value="" sx={{ fontSize }}>
              <Typography fontSize={fontSize} sx={{ color: colors.grey[500] }}>
                — none —
              </Typography>
            </MenuItem>
            {folders.map((folder) => (
              <MenuItem key={folder.id} value={folder.id} sx={{ fontSize, gap: "6px" }}>
                <Typography fontSize={fontSize} noWrap sx={{ flex: 1, color: colors.grey[100] }}>
                  {folder.name}
                </Typography>
                <Chip
                  label={`${folder.curve_count} curve${folder.curve_count !== 1 ? "s" : ""}`}
                  size="small"
                  sx={{
                    height: "16px",
                    fontSize: "9px",
                    backgroundColor: colors.blueAccent[700],
                    color: colors.grey[100],
                    flexShrink: 0,
                  }}
                />
              </MenuItem>
            ))}
          </Select>
        )}

        {/* New folder button */}
        <Tooltip title="New folder" placement="top">
          <IconButton
            size="small"
            onClick={() => setDialogOpen(true)}
            sx={{
              p: "2px",
              color: colors.grey[100],
              border: `1px solid ${colors.greenAccent[700]}`,
              borderRadius: "4px",
              "&:hover": { backgroundColor: colors.greenAccent[700] },
            }}
          >
            <AddIcon sx={{ fontSize: "14px" }} />
          </IconButton>
        </Tooltip>
      </Box>

      {/* New folder creation dialog */}
      <Dialog
        open={dialogOpen}
        onClose={handleCloseDialog}
        PaperProps={{
          sx: { backgroundColor: colors.primary[400], minWidth: "300px" },
        }}
      >
        <DialogTitle sx={{ color: colors.grey[100], pb: 1, fontSize: "15px" }}>
          New Folder
        </DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            fullWidth
            size="small"
            placeholder='e.g. "Collagen A 2026-06-18"'
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            // Allow submitting the form with Enter so the user doesn't have to click.
            onKeyDown={(e) => e.key === "Enter" && handleCreateFolder()}
            sx={{
              mt: 1,
              "& .MuiInputBase-input": { color: colors.grey[100], fontSize: "13px" },
              "& .MuiOutlinedInput-notchedOutline": { borderColor: colors.greenAccent[700] },
              "&:hover .MuiOutlinedInput-notchedOutline": { borderColor: colors.greenAccent[500] },
              "& .MuiInputBase-input::placeholder": { color: colors.grey[500], opacity: 1 },
            }}
          />
        </DialogContent>
        <DialogActions sx={{ px: 2, pb: 2 }}>
          <Button
            onClick={handleCloseDialog}
            sx={{ color: colors.grey[400], fontSize: "12px" }}
          >
            Cancel
          </Button>
          <Button
            onClick={handleCreateFolder}
            disabled={!newFolderName.trim() || creating}
            sx={{
              backgroundColor: colors.greenAccent[700],
              color: colors.grey[100],
              fontSize: "12px",
              "&:hover": { backgroundColor: colors.greenAccent[600] },
              "&.Mui-disabled": { opacity: 0.5, color: colors.grey[300] },
            }}
          >
            {creating ? (
              <CircularProgress size={14} sx={{ color: colors.grey[100] }} />
            ) : (
              "Create"
            )}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default FolderSelector;
