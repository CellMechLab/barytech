// DeviceData table — 3-level collapsible tree: Folder → Curve → Data rows.
// Fetches GET /api/device-data-grouped/ and flattens the response into the
// flat array that MUI DataGrid expects, inserting synthetic folder/curve header
// rows and expanding/collapsing them on click without any Pro licence.
import React, { useEffect, useState, useMemo, useCallback } from "react";
import { Box, Button, CircularProgress, IconButton, MenuItem, Select, Typography, Chip } from "@mui/material";
import { DataGrid, GridToolbarQuickFilter } from "@mui/x-data-grid";
import DeleteIcon from "@mui/icons-material/Delete";
import FileDownloadIcon from "@mui/icons-material/FileDownload";
import FolderOpenIcon from "@mui/icons-material/FolderOpen";
import TimelineIcon from "@mui/icons-material/Timeline";
import { tokens } from "../../theme";
import Header from "../dashboard/Header";
import { useTheme } from "@mui/material";
import axios from "axios";
import { toast, Toaster } from "sonner";
import { useNavigate } from "react-router-dom";
import { buildBackendUrl } from "../../config/endpoints";

// ── Helpers ───────────────────────────────────────────────────────────────────

// Formats an ISO datetime string to "DD/MM/YYYY HH:MM".
const formatDate = (isoString) => {
  if (!isoString) return "—";
  try {
    return new Date(isoString).toLocaleString("en-GB", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "—";
  }
};

// Returns the stable string key used for a folder's collapse/expand state.
const folderKey = (folderId) =>
  folderId != null ? `folder-${folderId}` : "folder-null";

// Returns the stable string key used for a curve's collapse/expand state.
const curveKey = (folderId, curveIndex) =>
  `curve-${folderId ?? "null"}-${curveIndex}`;

// ── Custom toolbar ────────────────────────────────────────────────────────────
// Rendered inside the DataGrid toolbar slot. Receives folders list and theme
// tokens as props because the toolbar is defined outside DeviceDataTable and
// therefore cannot close over the parent's state directly.

const DeviceDataToolbar = ({ folders, colors }) => {
  // ID of the folder selected for download; empty string = no selection.
  const [selectedFolderId, setSelectedFolderId] = useState("");
  // True while the HDF5 download fetch is in flight.
  const [downloading, setDownloading] = useState(false);

  // Derive the folder name so the downloaded file uses the correct filename.
  const selectedFolder = folders.find((f) => String(f.id) === String(selectedFolderId));

  const handleDownload = async () => {
    if (!selectedFolderId) return;
    setDownloading(true);
    try {
      // Reads the JWT stored at login so the export endpoint scopes data to this user.
      const token = sessionStorage.getItem("authToken");
      const res = await fetch(buildBackendUrl(`/api/export/folder/${selectedFolderId}`), {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!res.ok) {
        // Extract the backend's detail message so the user sees the real reason.
        let detail = `Export failed (${res.status})`;
        try {
          const errBody = await res.json();
          if (errBody?.detail) detail = errBody.detail;
        } catch (_) {}
        throw new Error(detail);
      }

      // Extract server-supplied filename from Content-Disposition or fall back to folder name.
      const disposition = res.headers.get("Content-Disposition") ?? "";
      const match = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
      const filename = match
        ? match[1].replace(/['"]/g, "")
        : `${selectedFolder?.name ?? `folder_${selectedFolderId}`}.hdf5`;

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      // Release the temporary object URL to free browser memory.
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error("[DeviceDataToolbar] download failed:", err);
      toast.error(err.message || "Failed to download HDF5. Please try again.", {
        style: { backgroundColor: "red", color: "white" },
      });
    } finally {
      setDownloading(false);
    }
  };

  return (
    <Box display="flex" alignItems="center" gap="12px" p="4px 8px">
      {/* Folder selector for export */}
      <Select
        value={selectedFolderId}
        onChange={(e) => setSelectedFolderId(e.target.value)}
        size="small"
        displayEmpty
        sx={{
          minWidth: 180,
          fontSize: "13px",
          height: "32px",
          color: colors.grey[100],
          ".MuiOutlinedInput-notchedOutline": { borderColor: colors.greenAccent[700] },
          "&:hover .MuiOutlinedInput-notchedOutline": { borderColor: colors.greenAccent[500] },
          ".MuiSvgIcon-root": { color: colors.grey[300] },
          backgroundColor: "transparent",
        }}
        MenuProps={{
          PaperProps: {
            sx: { backgroundColor: colors.primary[400] },
          },
        }}
      >
        {/* Disabled placeholder shown when nothing is selected */}
        <MenuItem value="" disabled sx={{ fontSize: "13px", color: colors.grey[500] }}>
          Select folder to export
        </MenuItem>
        {folders.map((folder) => (
          <MenuItem key={folder.id} value={String(folder.id)} sx={{ fontSize: "13px", gap: "8px" }}>
            <Typography fontSize="13px" sx={{ flex: 1, color: colors.grey[100] }}>
              {folder.name}
            </Typography>
            <Chip
              label={`${folder.curve_count}c`}
              size="small"
              sx={{
                height: "16px",
                fontSize: "9px",
                backgroundColor: colors.blueAccent[700],
                color: colors.grey[100],
              }}
            />
          </MenuItem>
        ))}
      </Select>

      {/* HDF5 download button */}
      <Button
        variant="contained"
        size="small"
        disabled={selectedFolderId === "" || downloading}
        onClick={handleDownload}
        startIcon={
          downloading
            ? <CircularProgress size={14} sx={{ color: "inherit" }} />
            : <FileDownloadIcon />
        }
        sx={{
          backgroundColor: colors.greenAccent[600],
          color: "#fff",
          fontWeight: 600,
          fontSize: "12px",
          textTransform: "none",
          height: "32px",
          "&:hover": { backgroundColor: colors.greenAccent[500] },
          "&.Mui-disabled": { backgroundColor: colors.grey[700], color: colors.grey[400] },
        }}
      >
        Download HDF5
      </Button>

      {/* Quick-filter pushed to the far right of the toolbar */}
      <Box sx={{ marginLeft: "auto" }}>
        <GridToolbarQuickFilter
          sx={{
            "& .MuiInputBase-input": { fontSize: "13px", color: colors.grey[100] },
            "& .MuiInputBase-root": { color: colors.grey[100] },
            "& .MuiSvgIcon-root": { color: colors.grey[400] },
          }}
        />
      </Box>
    </Box>
  );
};

// ── Component ─────────────────────────────────────────────────────────────────

const DeviceDataTable = () => {
  const theme = useTheme();
  // Colour palette resolved from the current light/dark theme mode.
  const colors = tokens(theme.palette.mode);
  const navigate = useNavigate();

  // Raw grouped data returned by GET /api/device-data-grouped/.
  const [groupedApiData, setGroupedApiData] = useState([]);
  // True while the initial or post-delete fetch is in flight.
  const [loading, setLoading] = useState(true);
  // IDs of selected data rows (integers only — folder/curve rows are excluded).
  const [selectionModel, setSelectionModel] = useState([]);

  // Set of folder row IDs (e.g. "folder-3") that are currently collapsed.
  // All folders start collapsed; individual toggle flips membership.
  const [collapsedFolders, setCollapsedFolders] = useState(() => new Set());
  // Set of curve row IDs (e.g. "curve-3-0") that are currently collapsed.
  const [collapsedCurves, setCollapsedCurves] = useState(() => new Set());

  // Folder list fetched on mount so the toolbar dropdown can populate its options.
  const [folders, setFolders] = useState([]);

  // ── Data fetching ───────────────────────────────────────────────────────────

  const fetchGroupedData = useCallback(async () => {
    setLoading(true);
    try {
      const token = sessionStorage.getItem("authToken");
      if (!token) {
        toast.error("You are not logged in. Please log in to view device data.", {
          style: { backgroundColor: "red", color: "white" },
        });
        navigate("/auth");
        return;
      }

      const response = await axios.get(
        buildBackendUrl("/api/device-data-grouped/"),
        { headers: { Authorization: `Bearer ${token}` } }
      );

      const data = response.data;
      setGroupedApiData(data);

      // Initialise collapse state: every folder and every curve starts collapsed.
      const allFolderKeys = new Set(data.map((f) => folderKey(f.folder_id)));
      const allCurveKeys = new Set(
        data.flatMap((f) =>
          f.curves.map((c) => curveKey(f.folder_id, c.curve_index))
        )
      );
      setCollapsedFolders(allFolderKeys);
      setCollapsedCurves(allCurveKeys);

      toast.success("Device data loaded.", {
        style: { backgroundColor: "green", color: "white" },
      });
    } catch (error) {
      if (error.response?.status === 401) {
        toast.error("Session expired. Please log in again.", {
          style: { backgroundColor: "red", color: "white" },
        });
        sessionStorage.removeItem("authToken");
        navigate("/auth");
      } else {
        toast.error("Failed to fetch device data. Please try again.", {
          style: { backgroundColor: "red", color: "white" },
        });
      }
    } finally {
      setLoading(false);
    }
  }, [navigate]);

  useEffect(() => {
    fetchGroupedData();
  }, [fetchGroupedData]);

  // Fetch folder metadata so the toolbar dropdown can list available folders.
  useEffect(() => {
    const fetchFolders = async () => {
      try {
        const token = sessionStorage.getItem("authToken");
        if (!token) return;
        const res = await axios.get(buildBackendUrl("/api/folders/"), {
          headers: { Authorization: `Bearer ${token}` },
        });
        setFolders(res.data);
      } catch (err) {
        // Non-critical — toolbar will simply show an empty dropdown if this fails.
        console.error("[DeviceDataTable] folder fetch failed:", err);
      }
    };
    fetchFolders();
  }, []);

  // ── Collapse toggles ────────────────────────────────────────────────────────

  // Toggles a folder and also collapses all of its child curves when closing,
  // so re-opening a folder always starts with curves collapsed.
  const toggleFolder = useCallback((fk, folder) => {
    setCollapsedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(fk)) {
        next.delete(fk);
      } else {
        next.add(fk);
        // Also collapse all curves inside this folder so they start fresh.
        setCollapsedCurves((prevC) => {
          const nextC = new Set(prevC);
          folder.curves.forEach((c) => nextC.add(curveKey(folder.folder_id, c.curve_index)));
          return nextC;
        });
      }
      return next;
    });
  }, []);

  // Toggles a single curve row independently of its parent folder.
  const toggleCurve = useCallback((ck) => {
    setCollapsedCurves((prev) => {
      const next = new Set(prev);
      if (next.has(ck)) next.delete(ck);
      else next.add(ck);
      return next;
    });
  }, []);

  // ── Delete handler ──────────────────────────────────────────────────────────

  const handleDelete = async () => {
    if (selectionModel.length === 0) {
      toast.error("No rows selected for deletion.", {
        style: { backgroundColor: "red", color: "white" },
      });
      return;
    }

    try {
      const token = sessionStorage.getItem("authToken");
      if (!token) {
        toast.error("You are not logged in. Please log in to delete data.", {
          style: { backgroundColor: "red", color: "white" },
        });
        navigate("/auth");
        return;
      }

      // Delete endpoint accepts an array of integer data-row IDs in the body.
      await axios.delete(buildBackendUrl("/api/device-data/"), {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        data: { ids: selectionModel },
      });

      toast.success("Selected rows deleted successfully!", {
        style: { backgroundColor: "green", color: "white" },
      });

      // Re-fetch so folder/curve row counts update automatically.
      setSelectionModel([]);
      await fetchGroupedData();
    } catch (error) {
      console.error("Error deleting rows:", error);
      toast.error("Failed to delete selected rows. Please try again.", {
        style: { backgroundColor: "red", color: "white" },
      });
    }
  };

  // ── Flatten grouped API data into a DataGrid-compatible array ───────────────
  //
  // Row shapes:
  //   Folder row : { id: "folder-N", isFolder: true, ... }
  //   Curve row  : { id: "curve-N-M", isCurve: true, ... }
  //   Data row   : { id: <int>, isData: true, device_id, timestamp, ... }

  const flatRows = useMemo(() => {
    const rows = [];

    groupedApiData.forEach((folder) => {
      const fk = folderKey(folder.folder_id);
      // Pre-compute total row count across all curves for the folder header chip.
      const totalRowCount = folder.curves.reduce((s, c) => s + c.row_count, 0);

      // ── Folder header row ─────────────────────────────────────────────────
      rows.push({
        id: fk,
        isFolder: true,
        // Carry the full folder object so toggleFolder can access its curves.
        _folder: folder,
        folder_id: folder.folder_id,
        folder_name: folder.folder_name,
        folder_created_at: folder.folder_created_at,
        curve_count: folder.curves.length,
        total_row_count: totalRowCount,
      });

      // Skip children if folder is collapsed.
      if (collapsedFolders.has(fk)) return;

      folder.curves.forEach((curve) => {
        const ck = curveKey(folder.folder_id, curve.curve_index);

        // ── Curve header row ────────────────────────────────────────────────
        rows.push({
          id: ck,
          isCurve: true,
          folder_id: folder.folder_id,
          curve_index: curve.curve_index,
          row_count: curve.row_count,
        });

        // Skip data rows if curve is collapsed.
        if (collapsedCurves.has(ck)) return;

        // ── Data rows ───────────────────────────────────────────────────────
        curve.rows.forEach((dataRow) => {
          rows.push({ ...dataRow, isData: true });
        });
      });
    });

    return rows;
  }, [groupedApiData, collapsedFolders, collapsedCurves]);

  // ── Selection: only integer data-row IDs reach the selection model ──────────

  const handleSelectionChange = useCallback((ids) => {
    // DataGrid passes string IDs for folder/curve rows and numbers for data rows.
    // Filter to only numeric IDs so group rows are never included.
    const dataIds = ids.filter((id) => typeof id === "number");
    setSelectionModel(dataIds);
  }, []);

  // ── Columns ─────────────────────────────────────────────────────────────────

  const columns = [
    {
      // "Name / Device" — the tree toggle column; renders all three row types.
      field: "device_id",
      headerName: "Name / Device",
      flex: 2,
      sortable: false,
      renderCell: (params) => {
        const { row } = params;

        // ── Folder header ────────────────────────────────────────────────────
        if (row.isFolder) {
          const isOpen = !collapsedFolders.has(row.id);
          return (
            <Box
              display="flex"
              alignItems="center"
              gap="8px"
              sx={{ cursor: "pointer", width: "100%", py: "2px" }}
              onClick={() => toggleFolder(row.id, row._folder)}
            >
              <FolderOpenIcon
                sx={{
                  fontSize: "15px",
                  color: theme.palette.mode === "light" ? colors.greenAccent[400] : colors.greenAccent[300],
                  flexShrink: 0,
                }}
              />
              <Typography
                fontWeight="bold"
                fontSize="13px"
                sx={{
                  color: theme.palette.mode === "light" ? colors.greenAccent[400] : colors.greenAccent[300],
                  flexShrink: 0,
                }}
              >
                {isOpen ? "▼" : "▶"} {row.folder_name}
              </Typography>
              {row.folder_created_at && (
                <Typography fontSize="11px" sx={{ color: colors.grey[500], flexShrink: 0 }}>
                  {formatDate(row.folder_created_at)}
                </Typography>
              )}
              <Chip
                label={`${row.curve_count} curve${row.curve_count !== 1 ? "s" : ""}`}
                size="small"
                sx={{
                  height: "18px", fontSize: "10px",
                  backgroundColor: theme.palette.mode === "light"
                    ? colors.blueAccent[700]
                    : colors.blueAccent[600],
                  color: theme.palette.mode === "light" ? colors.grey[100] : colors.grey[100],
                  flexShrink: 0,
                }}
              />
              <Chip
                label={`${row.total_row_count} rows`}
                size="small"
                sx={{
                  height: "18px", fontSize: "10px",
                  backgroundColor: theme.palette.mode === "light"
                    ? colors.greenAccent[600]
                    : colors.greenAccent[700],
                  color: colors.grey[100], flexShrink: 0,
                }}
              />
            </Box>
          );
        }

        // ── Curve header ─────────────────────────────────────────────────────
        if (row.isCurve) {
          const isOpen = !collapsedCurves.has(row.id);
          return (
            <Box
              display="flex"
              alignItems="center"
              gap="8px"
              pl="28px"
              sx={{ cursor: "pointer", width: "100%", py: "2px" }}
              onClick={() => toggleCurve(row.id)}
            >
              <TimelineIcon
                sx={{
                  fontSize: "14px",
                  color: theme.palette.mode === "light" ? colors.blueAccent[400] : colors.blueAccent[300],
                  flexShrink: 0,
                }}
              />
              <Typography
                fontSize="12px"
                sx={{
                  color: theme.palette.mode === "light" ? colors.blueAccent[400] : colors.blueAccent[300],
                  flexShrink: 0,
                }}
              >
                {isOpen ? "▼" : "▶"} Curve {row.curve_index}
              </Typography>
              <Chip
                label={`${row.row_count} rows`}
                size="small"
                sx={{
                  height: "18px", fontSize: "10px",
                  backgroundColor: theme.palette.mode === "light"
                    ? colors.blueAccent[600]
                    : colors.blueAccent[700],
                  color: colors.grey[100], flexShrink: 0,
                }}
              />
            </Box>
          );
        }

        // ── Data row ─────────────────────────────────────────────────────────
        return (
          <Typography fontSize="12px" pl="52px" sx={{ color: colors.grey[100] }}>
            {params.value}
          </Typography>
        );
      },
    },
    {
      field: "timestamp",
      headerName: "Timestamp",
      flex: 1,
      sortable: false,
      renderCell: (params) => {
        if (!params.row.isData) return null;
        return (
          <Typography fontSize="12px" sx={{ color: colors.grey[100] }}>
            {formatDate(params.value)}
          </Typography>
        );
      },
    },
    {
      field: "displacement",
      headerName: "Displacement",
      flex: 0.8,
      sortable: false,
      renderCell: (params) => {
        if (!params.row.isData) return null;
        return (
          <Typography fontSize="12px" sx={{ color: colors.grey[100] }}>
            {params.value} mm
          </Typography>
        );
      },
    },
    {
      field: "force",
      headerName: "Force",
      flex: 0.8,
      sortable: false,
      renderCell: (params) => {
        if (!params.row.isData) return null;
        return (
          <Typography fontSize="12px" sx={{ color: colors.grey[100] }}>
            {params.value} N
          </Typography>
        );
      },
    },
    {
      field: "delete",
      headerName: "Delete",
      width: 75,
      sortable: false,
      disableColumnMenu: true,
      // Header renders the delete action button so it's always visible.
      renderHeader: () => (
        <IconButton onClick={handleDelete} title="Delete Selected Rows">
          <DeleteIcon />
        </IconButton>
      ),
      // Data cells in this column are intentionally empty — delete is header-only.
      renderCell: () => null,
    },
  ];

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <Box m="20px">
      <Toaster />
      <Header title="DEVICE DATA" subtitle="Time-Series Data grouped by Folder → Curve" />
      <Box
        m="40px 0 0 0"
        height="75vh"
        sx={{
          "& .MuiDataGrid-root": {
            border: "none",
            color: colors.grey[100],
            backgroundColor: colors.primary[400],
          },
          "& .MuiDataGrid-cell": {
            borderBottom: `1px solid ${theme.palette.mode === "light" ? colors.grey[800] : colors.grey[700]}`,
            color: colors.grey[100],
          },
          "& .MuiDataGrid-columnHeaders": {
            backgroundColor: theme.palette.mode === "light"
              ? colors.blueAccent[800]
              : colors.blueAccent[700],
            borderBottom: "none",
            color: colors.grey[100],
          },
          "& .MuiDataGrid-columnHeaderTitle": {
            fontWeight: 600,
            color: colors.grey[100],
          },
          "& .MuiDataGrid-virtualScroller": {
            backgroundColor: colors.primary[400],
          },
          "& .MuiDataGrid-footerContainer": {
            borderTop: "none",
            backgroundColor: theme.palette.mode === "light"
              ? colors.blueAccent[800]
              : colors.blueAccent[700],
            color: colors.grey[100],
          },
          "& .MuiTablePagination-root, & .MuiTablePagination-displayedRows, & .MuiTablePagination-selectLabel": {
            color: colors.grey[100],
          },
          "& .MuiCheckbox-root": {
            color: `${colors.greenAccent[400]} !important`,
          },
          "& .MuiDataGrid-toolbarContainer": {
            backgroundColor: colors.primary[500],
            borderBottom: `1px solid ${theme.palette.mode === "light" ? colors.grey[800] : colors.grey[700]}`,
          },
          "& .MuiDataGrid-toolbarContainer .MuiButton-text": {
            color: `${colors.grey[100]} !important`,
          },
          // Default data rows — bright surface in light mode, not MUI's dark hover.
          "& .MuiDataGrid-row": {
            backgroundColor: colors.primary[400],
            "&:hover": {
              backgroundColor: colors.primary[500],
            },
            "&.Mui-hovered": {
              backgroundColor: `${colors.primary[500]} !important`,
            },
          },
          // Folder group rows — light green tint (light mode) / dark green (dark mode).
          "& .row-folder": {
            backgroundColor: colors.greenAccent[900],
            "&:hover": {
              backgroundColor: colors.greenAccent[800],
            },
            "&.Mui-hovered": {
              backgroundColor: `${colors.greenAccent[800]} !important`,
            },
          },
          // Curve group rows — light blue tint (light mode) / dark blue (dark mode).
          "& .row-curve": {
            backgroundColor: colors.blueAccent[900],
            "&:hover": {
              backgroundColor: colors.blueAccent[800],
            },
            "&.Mui-hovered": {
              backgroundColor: `${colors.blueAccent[800]} !important`,
            },
          },
        }}
      >
        <DataGrid
          rows={flatRows}
          columns={columns}
          checkboxSelection
          // Prevent folder and curve rows from being checked.
          isRowSelectable={(params) => !!params.row.isData}
          rowSelectionModel={selectionModel}
          onRowSelectionModelChange={handleSelectionChange}
          getRowId={(row) => row.id}
          loading={loading}
          // Row class names allow the sx above to target folder/curve rows.
          getRowClassName={(params) => {
            if (params.row.isFolder) return "row-folder";
            if (params.row.isCurve) return "row-curve";
            return "";
          }}
          // Custom toolbar provides folder-export dropdown + HDF5 download + quick filter.
          slots={{ toolbar: () => <DeviceDataToolbar folders={folders} colors={colors} /> }}
          // Disable built-in sorting so the pre-sorted tree order is preserved.
          sortingOrder={[]}
          disableColumnFilter={false}
        />
      </Box>
    </Box>
  );
};

export default DeviceDataTable;
