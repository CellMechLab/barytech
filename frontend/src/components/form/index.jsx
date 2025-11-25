import React from "react";
import { Box, Button, TextField } from "@mui/material";
import { useForm } from "react-hook-form";
import { yupResolver } from "@hookform/resolvers/yup";
import * as yup from "yup";
import useMediaQuery from "@mui/material/useMediaQuery";
import Header from "../dashboard/Header";
import axios from "axios";
import { toast, Toaster } from "sonner"; // Import Sonner's toast and Toaster
import { useNavigate } from "react-router-dom"; // For navigation

const IoTDeviceForm = () => {
  const isNonMobile = useMediaQuery("(min-width:600px)");
  const navigate = useNavigate(); // For redirecting to the login page

  // Use React Hook Form
  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
  } = useForm({
    defaultValues: initialValues,
    resolver: yupResolver(deviceSchema), // Use Yup for validation
  });

  // Handle form submission
  const onSubmit = async (data) => {
    try {
      const token = sessionStorage.getItem("authToken");
      if (!token) {
        toast.error("You are not logged in. Please log in to create a device.", {
          style: { backgroundColor: "red", color: "white" },
        });
        return;
      }

      const requestData = {
        device_name: data.device_name,
        device_type: data.device_type,
      };

      const response = await axios.post("http://127.0.0.1:8000/api/devices/", requestData, {
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
      });

      toast.success("Device created successfully!", {
        style: { backgroundColor: "green", color: "white" },
      });
      reset(); // Reset form fields
    } catch (error) {
      if (error.response && error.response.status === 401) {
        toast.error("Session expired. Please log in again.", {
          style: { backgroundColor: "red", color: "white" },
        });
        sessionStorage.removeItem("authToken");
        navigate("/auth"); // Redirect to login page
      } else {
        toast.error("Failed to create device. Please try again.", {
          style: { backgroundColor: "red", color: "white" },
        });
      }
      console.error("Error creating device:", error);
    }
  };

  return (
    <Box m="20px">
      <Header title="CREATE DEVICE" subtitle="Create a New IoT Device Record" />
      <form onSubmit={handleSubmit(onSubmit)}>
        <Box
          display="grid"
          gap="30px"
          gridTemplateColumns="repeat(4, minmax(0, 1fr))"
          sx={{
            "& > div": { gridColumn: isNonMobile ? undefined : "span 4" },
          }}
        >
          <TextField
            fullWidth
            variant="filled"
            type="text"
            label="Device Name"
            {...register("device_name")}
            error={!!errors.device_name}
            helperText={errors.device_name?.message}
            sx={{ gridColumn: "span 4" }}
          />
          <TextField
            fullWidth
            variant="filled"
            type="text"
            label="Device Type"
            {...register("device_type")}
            error={!!errors.device_type}
            helperText={errors.device_type?.message}
            sx={{ gridColumn: "span 4" }}
          />
        </Box>
        <Box display="flex" justifyContent="end" mt="20px">
          <Button type="submit" color="secondary" variant="contained">
            Create IoT Device
          </Button>
        </Box>
      </form>
    </Box>
  );
};

// Validation schema using Yup
const deviceSchema = yup.object().shape({
  device_name: yup.string().required("Device name is required"),
  device_type: yup
    .string()
    .oneOf(["sensor", "actuator"], "Invalid device type")
    .required("Device type is required"),
});

const initialValues = {
  device_name: "",
  device_type: "",
};

export default IoTDeviceForm;
