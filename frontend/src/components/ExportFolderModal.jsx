// Modal to review and edit experiment metadata before saving and downloading HDF5.
import React, { useEffect, useState } from "react";
import {
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Select,
  TextField,
  Typography,
} from "@mui/material";
import { toast } from "sonner";
import { buildBackendUrl } from "../config/endpoints";

// Allowed probe tip shapes for HDF5 tip geometry export.
const TIP_GEOMETRY_OPTIONS = ["sphere", "cone", "cylinder", "pyramid"];

// Scale factors: display value = stored SI value × storageScale.
const METERS_TO_MICROMETERS = 1e6;
const METERS_TO_MILLIMETERS = 1e3;

// Metadata fields shown in the export modal (Z conversion uses backend default only).
const EXPORT_METADATA_FIELDS = [
  {
    key: "velocity",
    label: "Velocity (µm/s)",
    inputType: "number",
    storageScale: METERS_TO_MICROMETERS,
  },
  {
    key: "force_conversion_factor",
    label: "Force conversion coefficient (N/mm)",
    inputType: "number",
  },
  { key: "spring_constant", label: "Spring constant (N/m)", inputType: "number" },
  { key: "sensor_type", label: "Sensor type", inputType: "text" },
  { key: "tip_geometry", label: "Probe tip shape", inputType: "select" },
  {
    key: "tip_radius",
    label: "Tip radius (mm)",
    inputType: "number",
    storageScale: METERS_TO_MILLIMETERS,
  },
];

// Reads the JWT stored at login for authenticated backend requests.
const getAuthToken = () => sessionStorage.getItem("authToken");

/**
 * ExportFolderModal — confirm/edit experiment metadata, save to folder, download HDF5.
 *
 * @param {boolean} open - Whether the dialog is visible.
 * @param {Function} onClose - Called when the user dismisses the dialog.
 * @param {number|string|null} folderId - Folder to export.
 * @param {string|null} folderName - Display name for the folder.
 * @param {object} colors - Theme token palette from tokens().
 * @param {Function} [onExportingChange] - Notifies parent when export is in progress.
 */
const ExportFolderModal = ({
  open,
  onClose,
  folderId,
  folderName,
  colors,
  onExportingChange,
}) => {
  // True while export metadata is being loaded from the backend.
  const [metadataLoading, setMetadataLoading] = useState(false);
  // True while metadata save + HDF5 download is in flight.
  const [exporting, setExporting] = useState(false);
  // Form values for experiment metadata embedded in the HDF5 file.
  const [metadataForm, setMetadataForm] = useState({});

  useEffect(() => {
    if (!open || !folderId) return;

    const loadMetadata = async () => {
      setMetadataLoading(true);
      try {
        const token = getAuthToken();
        const res = await fetch(
          buildBackendUrl(`/api/folders/${folderId}/export-metadata`),
          { headers: { Authorization: `Bearer ${token}` } },
        );
        if (!res.ok) {
          let detail = `Failed to load metadata (${res.status})`;
          try {
            const errBody = await res.json();
            if (errBody?.detail) detail = errBody.detail;
          } catch (_) {}
          throw new Error(detail);
        }
        const metadata = await res.json();
        const loadedTipGeometry = String(metadata.tip_geometry ?? "sphere").toLowerCase();
        setMetadataForm({
          velocity: metadata.velocity * METERS_TO_MICROMETERS,
          force_conversion_factor: metadata.force_conversion_factor,
          spring_constant: metadata.spring_constant,
          sensor_type: metadata.sensor_type,
          tip_geometry: TIP_GEOMETRY_OPTIONS.includes(loadedTipGeometry)
            ? loadedTipGeometry
            : "sphere",
          tip_radius: metadata.tip_radius * METERS_TO_MILLIMETERS,
        });
      } catch (err) {
        console.error("[ExportFolderModal] metadata load failed:", err);
        toast.error(err.message || "Failed to load export metadata.", {
          style: { backgroundColor: "red", color: "white" },
        });
        onClose();
      } finally {
        setMetadataLoading(false);
      }
    };

    loadMetadata();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, folderId]);

  const buildMetadataPayload = () => {
    const payload = {};
    EXPORT_METADATA_FIELDS.forEach(({ key, inputType, storageScale }) => {
      const raw = metadataForm[key];
      if (raw === "" || raw == null) return;
      let value = inputType === "number" ? Number(raw) : raw;
      if (storageScale) {
        value = value / storageScale;
      }
      payload[key] = value;
    });
    return payload;
  };

  const handleConfirmExport = async () => {
    if (!folderId) return;
    setExporting(true);
    onExportingChange?.(true);
    try {
      const token = getAuthToken();

      const saveRes = await fetch(
        buildBackendUrl(`/api/folders/${folderId}/metadata`),
        {
          method: "PATCH",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify(buildMetadataPayload()),
        },
      );
      if (!saveRes.ok) {
        let detail = `Failed to save metadata (${saveRes.status})`;
        try {
          const errBody = await saveRes.json();
          if (errBody?.detail) detail = errBody.detail;
        } catch (_) {}
        throw new Error(detail);
      }

      const exportRes = await fetch(buildBackendUrl(`/api/export/folder/${folderId}`), {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!exportRes.ok) {
        let detail = `Export failed (${exportRes.status})`;
        try {
          const errBody = await exportRes.json();
          if (errBody?.detail) detail = errBody.detail;
        } catch (_) {}
        throw new Error(detail);
      }

      const disposition = exportRes.headers.get("Content-Disposition") ?? "";
      const match = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
      const filename = match
        ? match[1].replace(/['"]/g, "")
        : `${folderName ?? `folder_${folderId}`}.hdf5`;

      const blob = await exportRes.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);

      toast.success("HDF5 exported successfully.", {
        style: { backgroundColor: "green", color: "white" },
      });
      onClose();
    } catch (err) {
      console.error("[ExportFolderModal] export failed:", err);
      toast.error(err.message || "Failed to export HDF5. Please try again.", {
        style: { backgroundColor: "red", color: "white" },
      });
    } finally {
      setExporting(false);
      onExportingChange?.(false);
    }
  };

  const handleClose = () => {
    if (exporting) return;
    onClose();
  };

  const textFieldSx = {
    "& .MuiInputBase-input": { color: colors.grey[100], fontSize: "13px" },
    "& .MuiInputLabel-root": { color: colors.grey[400], fontSize: "13px" },
    "& .MuiOutlinedInput-notchedOutline": { borderColor: colors.greenAccent[700] },
    "&:hover .MuiOutlinedInput-notchedOutline": { borderColor: colors.greenAccent[500] },
  };

  const selectFieldSx = {
    ...textFieldSx,
    "& .MuiSvgIcon-root": { color: colors.grey[300] },
  };

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      maxWidth="sm"
      fullWidth
      PaperProps={{
        sx: { backgroundColor: colors.primary[400] },
      }}
    >
      <DialogTitle sx={{ color: colors.grey[100], pb: 1, fontSize: "15px" }}>
        Export experiment — {folderName ?? "folder"}
      </DialogTitle>
      <DialogContent>
        <Typography sx={{ color: colors.grey[400], fontSize: "12px", mb: 2 }}>
          Review metadata that will be written into every curve&apos;s HDF5 tip group.
          Edit values if needed, then confirm to save and download.
        </Typography>
        {metadataLoading ? (
          <Box display="flex" justifyContent="center" py={4}>
            <CircularProgress size={28} sx={{ color: colors.greenAccent[500] }} />
          </Box>
        ) : (
          <Grid container spacing={2}>
            {EXPORT_METADATA_FIELDS.map(({ key, label, inputType }) => (
              <Grid item xs={12} sm={6} key={key}>
                {inputType === "select" ? (
                  <FormControl fullWidth size="small" disabled={exporting} sx={selectFieldSx}>
                    <InputLabel id={`${key}-label`}>{label}</InputLabel>
                    <Select
                      labelId={`${key}-label`}
                      label={label}
                      value={metadataForm[key] ?? "sphere"}
                      onChange={(e) =>
                        setMetadataForm((prev) => ({ ...prev, [key]: e.target.value }))
                      }
                      MenuProps={{
                        PaperProps: {
                          sx: { backgroundColor: colors.primary[400] },
                        },
                      }}
                    >
                      {TIP_GEOMETRY_OPTIONS.map((option) => (
                        <MenuItem
                          key={option}
                          value={option}
                          sx={{ fontSize: "13px", color: colors.grey[100], textTransform: "capitalize" }}
                        >
                          {option}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                ) : (
                  <TextField
                    fullWidth
                    size="small"
                    label={label}
                    type={inputType}
                    value={metadataForm[key] ?? ""}
                    onChange={(e) =>
                      setMetadataForm((prev) => ({ ...prev, [key]: e.target.value }))
                    }
                    disabled={exporting}
                    sx={textFieldSx}
                  />
                )}
              </Grid>
            ))}
          </Grid>
        )}
      </DialogContent>
      <DialogActions sx={{ px: 2, pb: 2 }}>
        <Button
          onClick={handleClose}
          disabled={exporting}
          sx={{ color: colors.grey[400], fontSize: "12px" }}
        >
          Cancel
        </Button>
        <Button
          onClick={handleConfirmExport}
          disabled={metadataLoading || exporting}
          sx={{
            backgroundColor: colors.greenAccent[700],
            color: colors.grey[100],
            fontSize: "12px",
            "&:hover": { backgroundColor: colors.greenAccent[600] },
            "&.Mui-disabled": { opacity: 0.5, color: colors.grey[300] },
          }}
        >
          {exporting ? (
            <CircularProgress size={14} sx={{ color: colors.grey[100] }} />
          ) : (
            "Save & Download HDF5"
          )}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default ExportFolderModal;
