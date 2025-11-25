import React, { useState, useEffect } from "react";
import { Box, IconButton } from "@mui/material";
import { DataGrid, GridToolbar } from "@mui/x-data-grid";
import DeleteIcon from "@mui/icons-material/Delete";
import { tokens } from "../../theme";
import Header from "../dashboard/Header";
import { useTheme } from "@mui/material";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import VisibilityIcon from "@mui/icons-material/Visibility";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import axios from "axios";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";

const IoTDevices = () => {
  const theme = useTheme();
  const colors = tokens(theme.palette.mode);
  const navigate = useNavigate();

  const [visibleTokens, setVisibleTokens] = useState({});
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectionModel, setSelectionModel] = useState([]); // Tracks selected rows for deletion

  useEffect(() => {
    const fetchDevices = async () => {
      try {
        const token = sessionStorage.getItem("authToken");
        if (!token) {
          toast.error("You are not logged in. Please log in to view devices.", {
            style: { backgroundColor: "red", color: "white" },
          });
          navigate("/auth");
          return;
        }

        const response = await axios.get("http://127.0.0.1:8000/api/devices/", {
          headers: { Authorization: `Bearer ${token}` },
        });

        setDevices(response.data);
        toast.success("Devices fetched successfully!", {
          style: { backgroundColor: "green", color: "white" },
        });
      } catch (error) {
        if (error.response && error.response.status === 401) {
          toast.error("Session expired. Please log in again.", {
            style: { backgroundColor: "red", color: "white" },
          });
          sessionStorage.removeItem("authToken");
          navigate("/auth");
        } else {
          toast.error("Failed to fetch devices. Please try again.", {
            style: { backgroundColor: "red", color: "white" },
          });
        }
      } finally {
        setLoading(false);
      }
    };

    fetchDevices();
  }, [navigate]);

  const handleCopy = (text) => {
    navigator.clipboard.writeText(text);
    toast.success(`Copied: ${text}`, {
      style: { backgroundColor: "blue", color: "white" },
    });
  };

  const toggleTokenVisibility = (deviceId) => {
    setVisibleTokens((prev) => ({
      ...prev,
      [deviceId]: !prev[deviceId],
    }));
  };

  const handleDelete = async () => {
    console.log("handleDelete", selectionModel.length)
    if (selectionModel.length === 0) {
      toast.error("No devices selected for deletion.", {
        style: { backgroundColor: "red", color: "white" },
      });
      return;
    }

    try {
      const token = sessionStorage.getItem("authToken");
      if (!token) {
        toast.error("You are not logged in. Please log in to delete devices.", {
          style: { backgroundColor: "red", color: "white" },
        });
        navigate("/auth");
        return;
      }
      console.log("selection", selectionModel)
      await axios.delete("http://127.0.0.1:8000/api/devices/", {
        headers: { Authorization: `Bearer ${token}` },
        data: { device_ids: selectionModel }, // Pass selected IDs in the request body
      });
  

      // Remove deleted devices from the state
      setDevices((prevDevices) =>
        prevDevices.filter((device) => !selectionModel.includes(device.id))
      );

      toast.success("Selected devices deleted successfully!", {
        style: { backgroundColor: "green", color: "white" },
      });

      setSelectionModel([]);
    } catch (error) {
      toast.error("Failed to delete devices. Please try again.", {
        style: { backgroundColor: "red", color: "white" },
      });
    }
  };

  const columns = [
    {
      field: "id",
      headerName: "Device ID",
      flex: 1,
      renderCell: (params) => (
        <Box display="flex" alignItems="center" gap={1}>
          <span>{params.value}</span>
          <IconButton
            size="small"
            onClick={() => handleCopy(params.value)}
            title="Copy Device ID"
          >
            <ContentCopyIcon fontSize="small" />
          </IconButton>
        </Box>
      ),
    },
    {
      field: "device_name",
      headerName: "Device Name",
      flex: 1,
      cellClassName: "name-column--cell",
    },
    { field: "device_type", headerName: "Device Type", flex: 1 },
    {
      field: "status",
      headerName: "Status",
      flex: 0.5,
      cellClassName: (params) =>
        params.value === "Online" ? "status-online" : "status-offline",
    },
    {
      field: "created_at",
      headerName: "Created At",
      flex: 1,
      renderCell: (params) => {
        const date = new Date(params.value);
        return date.toLocaleString("en-GB", {
          day: "2-digit",
          month: "2-digit",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        });
      },
    },
    {
      field: "device_token",
      headerName: "Device Token",
      flex: 1.5,
      renderCell: (params) => {
        const isVisible = visibleTokens[params.row.device_id];
        return (
          <Box display="flex" alignItems="center" gap={1}>
            <span>{isVisible ? params.value : "••••••••••••"}</span>
            <IconButton
              size="small"
              onClick={() => toggleTokenVisibility(params.row.device_id)}
              title={isVisible ? "Hide Token" : "Show Token"}
            >
              {isVisible ? (
                <VisibilityOffIcon fontSize="small" />
              ) : (
                <VisibilityIcon fontSize="small" />
              )}
            </IconButton>
            <IconButton
              size="small"
              onClick={() => handleCopy(params.value)}
              title="Copy Device Token"
            >
              <ContentCopyIcon fontSize="small" />
            </IconButton>
          </Box>
        );
      },
    },
    {
      field: "delete",
      headerName: "Delete",
      width: 75,
      sortable: false,
      disableColumnMenu: true,
      renderHeader: () => (
        <IconButton onClick={handleDelete} title="Delete Selected Devices">
          <DeleteIcon />
        </IconButton>
      ),
    },
  ];

  return (
    <Box m="20px">
      <Header title="IoT DEVICES" subtitle="List of Your IoT Devices" />
      <Box
        m="40px 0 0 0"
        height="75vh"
        sx={{
          "& .MuiDataGrid-root": { border: "none" },
          "& .MuiDataGrid-cell": { borderBottom: "none" },
          "& .name-column--cell": { color: colors.greenAccent[300] },
          "& .status-online": { color: colors.greenAccent[400] },
          "& .status-offline": { color: colors.redAccent[400] },
          "& .MuiDataGrid-columnHeaders": {
            backgroundColor: colors.blueAccent[700],
            borderBottom: "none",
          },
          "& .MuiDataGrid-virtualScroller": { backgroundColor: colors.primary[400] },
          "& .MuiDataGrid-footerContainer": {
            borderTop: "none",
            backgroundColor: colors.blueAccent[700],
          },
          "& .MuiCheckbox-root": { color: `${colors.greenAccent[200]} !important` },
          "& .MuiDataGrid-toolbarContainer .MuiButton-text": {
            color: `${colors.grey[100]} !important`,
          },
        }}
      >
        <DataGrid
          rows={devices}
          columns={columns}
          checkboxSelection
          disableRowSelectionOnClick
          selectionModel={selectionModel} // Controlled selection model
          onRowSelectionModelChange ={(newSelection) => {
            setSelectionModel(newSelection); // Update the selection model
          }}
          getRowId={(row) => row.id}
          slots={{
            toolbar: GridToolbar,
          }}
          loading={loading}
          slotProps={{
            toolbar: {
              showQuickFilter: true,
            },
          }}
        />
      </Box>
    </Box>
  );
};

export default IoTDevices;
