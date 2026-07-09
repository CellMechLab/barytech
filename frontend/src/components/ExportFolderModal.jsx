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
  Grid,
  TextField,
  Typography,
} from "@mui/material";
import { toast } from "sonner";
import { buildBackendUrl } from "../config/endpoints";

// Metadata fields written into every curve's HDF5 tip group on export.
const EXPORT_METADATA_FIELDS = [
  { key: "velocity", label: "Velocity (m/s)", inputType: "number" },
  { key: "force_conversion_factor", label: "Force conversion factor", inputType: "number" },
  { key: "z_conversion_factor", label: "Z conversion factor", inputType: "number" },
  { key: "spring_constant", label: "Spring constant (N/m)", inputType: "number" },
  { key: "tip_geometry", label: "Tip geometry", inputType: "text" },
  { key: "tip_radius", label: "Tip radius (m)", inputType: "number" },
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
        setMetadataForm({
          velocity: metadata.velocity,
          force_conversion_factor: metadata.force_conversion_factor,
          z_conversion_factor: metadata.z_conversion_factor,
          spring_constant: metadata.spring_constant,
          tip_geometry: metadata.tip_geometry,
          tip_radius: metadata.tip_radius,
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
    EXPORT_METADATA_FIELDS.forEach(({ key, inputType }) => {
      const raw = metadataForm[key];
      if (raw === "" || raw == null) return;
      payload[key] = inputType === "number" ? Number(raw) : raw;
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
