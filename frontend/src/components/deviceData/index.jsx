import React, { useEffect, useState } from "react";
import { Box, IconButton, CircularProgress } from "@mui/material";
import { DataGrid, GridToolbar } from "@mui/x-data-grid";
import DeleteIcon from "@mui/icons-material/Delete";
import { tokens } from "../../theme";
import Header from "../dashboard/Header";
import { useTheme } from "@mui/material";
import axios from "axios";
import { toast, Toaster } from "sonner";
import { useNavigate } from "react-router-dom";

const DeviceDataTable = () => {
  const theme = useTheme();
  const colors = tokens(theme.palette.mode);
  const navigate = useNavigate();

  const [deviceData, setDeviceData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [selectionModel, setSelectionModel] = useState([]);
  const [collapsedGroups, setCollapsedGroups] = useState({});

  useEffect(() => {
    const fetchDeviceData = async () => {
      try {
        const token = sessionStorage.getItem("authToken");
        if (!token) {
          toast.error(
            "You are not logged in. Please log in to view device data.",
            {
              style: { backgroundColor: "red", color: "white" },
            }
          );
          navigate("/auth");
          return;
        }

        const response = await axios.get(
          "http://127.0.0.1:8000/api/device-data/",
          {
            headers: {
              Authorization: `Bearer ${token}`,
            },
          }
        );

        setDeviceData(response.data);
        toast.success("Device data fetched successfully!", {
          style: { backgroundColor: "green", color: "white" },
        });

        const initialCollapsedState = {};
        response.data.forEach((item) => {
          initialCollapsedState[item.device_id] = true;
        });
        setCollapsedGroups(initialCollapsedState);
      } catch (error) {
        if (error.response && error.response.status === 401) {
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
    };

    fetchDeviceData();
  }, [navigate]);

  const handleDelete = async () => {
    if (selectionModel.length === 0) {
      toast.error("No devices selected for deletion.", {
        style: { backgroundColor: "red", color: "white" },
      });
      return;
    }

    // 🔍 Collect all device_ids from selection
    const selectedDeviceIdsSet = new Set();

    selectionModel.forEach((rowId) => {
      // Group row: id = "group-<device_id>"
      if (typeof rowId === "string" && rowId.startsWith("group-")) {
        const deviceId = rowId.replace("group-", "");
        selectedDeviceIdsSet.add(deviceId);
      } else {
        // Data row: id = DeviceData.id (integer)
        const row = deviceData.find((r) => r.id === rowId);
        if (row && row.device_id) {
          selectedDeviceIdsSet.add(row.device_id);
        }
      }
    });

    const selectedDeviceIds = Array.from(selectedDeviceIdsSet);

    if (selectedDeviceIds.length === 0) {
      toast.error("No device IDs resolved from selection.", {
        style: { backgroundColor: "red", color: "white" },
      });
      return;
    }

    setDeleting(true);
    const loadingToast = toast.loading("Deleting device data by device...", {
      style: { backgroundColor: "orange", color: "white" },
    });

    try {
      const token = sessionStorage.getItem("authToken");
      if (!token) {
        toast.dismiss(loadingToast);
        toast.error("You are not logged in. Please log in to delete data.", {
          style: { backgroundColor: "red", color: "white" },
        });
        navigate("/auth");
        return;
      }

      // 🔥 Call your new bulk endpoint per device (DB delete is bulk inside)
      await Promise.all(
        selectedDeviceIds.map((deviceId) =>
          axios.delete(
            `http://127.0.0.1:8000/api/device-data/by-device/${encodeURIComponent(
              deviceId
            )}`,
            {
              headers: {
                Authorization: `Bearer ${token}`,
              },
            }
          )
        )
      );

      // 🧹 Remove all rows for those devices from the table
      setDeviceData((prev) =>
        prev.filter((row) => !selectedDeviceIdsSet.has(row.device_id))
      );

      toast.dismiss(loadingToast);
      toast.success(
        `All data deleted for ${selectedDeviceIds.length} device(s).`,
        {
          style: { backgroundColor: "green", color: "white" },
        }
      );

      setSelectionModel([]);
    } catch (error) {
      console.error("Error deleting device data by device:", error);
      toast.dismiss(loadingToast);
      toast.error("Failed to delete device data. Please try again.", {
        style: { backgroundColor: "red", color: "white" },
      });
    } finally {
      setDeleting(false);
    }
  };
  

  const groupedData = React.useMemo(() => {
    const grouped = {};
    deviceData.forEach((item) => {
      if (!grouped[item.device_id]) {
        grouped[item.device_id] = [];
      }
      grouped[item.device_id].push(item);
    });

    const rows = [];
    Object.keys(grouped).forEach((deviceId) => {
      rows.push({
        id: `group-${deviceId}`,
        device_id: deviceId,
        isGroup: true,
      });
      if (!collapsedGroups[deviceId]) {
        grouped[deviceId].forEach((data) => rows.push(data));
      }
    });

    return rows;
  }, [deviceData, collapsedGroups]);

  const handleToggleGroup = (deviceId) => {
    setCollapsedGroups((prev) => ({
      ...prev,
      [deviceId]: !prev[deviceId],
    }));
  };

  const handleSelectionChange = (ids) => {
    const selectedIDs = new Set(ids);
    const expandedSelection = new Set(selectedIDs);

    // Add all child row IDs if a group row is selected
    groupedData.forEach((row) => {
      if (row.isGroup && selectedIDs.has(row.id)) {
        const groupID = row.device_id;
        deviceData
          .filter((item) => item.device_id === groupID)
          .forEach((childRow) => {
            expandedSelection.add(childRow.id); // use DB id
          });
      }
    });

    setSelectionModel(Array.from(expandedSelection));
  };

  const columns = [
    {
      field: "device_id",
      headerName: "Device ID",
      flex: 1,
      renderCell: (params) => {
        if (params.row.isGroup) {
          return (
            <strong
              style={{ cursor: "pointer", color: colors.greenAccent[400] }}
              onClick={() => handleToggleGroup(params.row.device_id)}
            >
              {collapsedGroups[params.row.device_id] ? "▶" : "▼"} Device ID:{" "}
              {params.row.device_id}
            </strong>
          );
        }
        return <span>{params.value}</span>;
      },
    },
    {
      field: "timestamp",
      headerName: "Timestamp",
      flex: 1,
      renderCell: (params) => {
        if (params.row.isGroup) return null;
        const date = new Date(params.value);
        const formattedDate = date.toLocaleString("en-GB", {
          day: "2-digit",
          month: "2-digit",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        });
        return <span>{formattedDate}</span>;
      },
    },
    {
      field: "displacement",
      headerName: "Displacement",
      flex: 1,
      renderCell: (params) =>
        params.row.isGroup ? null : <span>{params.value} mm</span>,
    },
    {
      field: "force",
      headerName: "Force",
      flex: 1,
      renderCell: (params) =>
        params.row.isGroup ? null : <span>{params.value} N</span>,
    },
    {
      field: "delete",
      headerName: "Delete",
      width: 75,
      sortable: false,
      disableColumnMenu: true,
      renderHeader: () => (
        <IconButton 
          onClick={handleDelete} 
          title="Delete Selected Rows"
          disabled={deleting}
        >
          {deleting ? (
            <CircularProgress size={24} color="inherit" />
          ) : (
            <DeleteIcon />
          )}
        </IconButton>
      ),
    },
  ];

  return (
    <Box m="20px">
      <Header title="DEVICE DATA" subtitle="Time-Series Data for IoT Devices" />
      <Box
        m="40px 0 0 0"
        height="75vh"
        sx={{
          "& .MuiDataGrid-root": {
            border: "none",
          },
          "& .MuiDataGrid-cell": {
            borderBottom: "none",
          },
          "& .MuiDataGrid-columnHeaders": {
            backgroundColor: colors.blueAccent[700],
            borderBottom: "none",
          },
          "& .MuiDataGrid-virtualScroller": {
            backgroundColor: colors.primary[400],
          },
          "& .MuiDataGrid-footerContainer": {
            borderTop: "none",
            backgroundColor: colors.blueAccent[700],
          },
          "& .MuiCheckbox-root": {
            color: `${colors.greenAccent[200]} !important`,
          },
          "& .MuiDataGrid-toolbarContainer .MuiButton-text": {
            color: `${colors.grey[100]} !important`,
          },
        }}
      >
        <DataGrid
          rows={groupedData}
          columns={columns}
          checkboxSelection
          onRowSelectionModelChange={(ids) => handleSelectionChange(ids)}
          getRowId={(row) => {
            // Group row keeps its custom string ID
            if (row.isGroup) {
              return row.id; // e.g. "group-frontend1_ultra_high_perf_device"
            }
            // Data rows use their DB primary key
            return row.id;   // DeviceData.id (integer)
          }}
          components={{ Toolbar: GridToolbar }}
          loading={loading}
          disableSelectionOnClick
          slots={{
            toolbar: GridToolbar,
          }}
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

export default DeviceDataTable;
