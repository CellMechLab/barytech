import React, { useEffect, useState } from "react";
import { Box, IconButton } from "@mui/material";
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
  
    try {
      const token = sessionStorage.getItem("authToken");
      if (!token) {
        toast.error("You are not logged in. Please log in to delete data.", {
          style: { backgroundColor: "red", color: "white" },
        });
        navigate("/auth");
        return;
      }
  
      // Send a single delete request with an array of IDs in the body
      await axios.delete("http://127.0.0.1:8000/api/device-data/", {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        data: { ids: selectionModel }, // Pass selected IDs in the request body
      });
  
      // Remove deleted devices from the state
      setDeviceData((prev) =>
        prev.filter((device) => !selectionModel.includes(device.id))
      );
  
      toast.success("Selected rows deleted successfully!", {
        style: { backgroundColor: "green", color: "white" },
      });
  
      setSelectionModel([]); // Clear selection
    } catch (error) {
      console.error("Error deleting devices:", error);
      toast.error("Failed to delete selected rows. Please try again.", {
        style: { backgroundColor: "red", color: "white" },
      });
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
    console.log("handle");
    const selectedIDs = new Set(ids);

    const expandedSelection = [...selectedIDs];

    // Add all child rows if a group row is selected
    groupedData.forEach((row) => {
      if (row.isGroup && selectedIDs.has(row.id)) {
        const groupID = row.device_id;
        deviceData
          .filter((item) => item.device_id === groupID)
          .forEach((childRow) => expandedSelection.push(childRow.id));
      }
    });
    console.log(expandedSelection);
    setSelectionModel(expandedSelection);
  };

  const columns = [
    { field: "id", headerName: "Data ID", flex: 0.5, hide: true },
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
        <IconButton onClick={handleDelete} title="Delete Selected Rows">
          <DeleteIcon />
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
          getRowId={(row) => row.id}
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
