import React, { useState, useEffect } from "react";
import { Box, Button } from "@mui/material";
import Login from "./Login";
import Register from "./Register";
import { useNavigate,useLocation } from "react-router-dom"; // Import useNavigate
import { useUser } from "../../context/UserContext"; // Import your UserContext

const AuthPage = () => {
  const [isLogin, setIsLogin] = useState(true);
  const navigate = useNavigate();
  const { login } = useUser(); // Get the login function from UserContext
  const location = useLocation();
  useEffect(() => {
    const token = sessionStorage.getItem("authToken");
    if (token) {
      const fetchUser = async () => {
        try {
          const response = await fetch("http://localhost:8000/me", {
            headers: {
              Authorization: `Bearer ${token}`,
            },
          });

          if (response.ok) {
            const userData = await response.json();
            console.log("User data restored:", userData);

            // Redirect to dashboard if session is valid
            if (location.pathname !== "/") {
              console.log("navigate")
              login({ username: userData.username, user_id: userData.user_id })
              navigate("/");
            }
          } else {
            console.error("Failed to validate token. Logging out.");
            sessionStorage.removeItem("authToken"); // Clear invalid token
          }
        } catch (error) {
          console.error("Error restoring session:", error);
          sessionStorage.removeItem("authToken");
        }
      };

      fetchUser();
    }
  },[location.pathname, navigate, login]);
  const toggleAuthMode = () => {
    setIsLogin((prevMode) => !prevMode);
  };

  const handleLoginSubmit = async (data) => {
    try {
      const response = await fetch("http://localhost:8000/token", {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: new URLSearchParams(data),
      });

      if (response.ok) {
        const result = await response.json();
        console.log("Login successful:", result.access_token);
        // Save the token to localStorage
        sessionStorage.setItem("authToken", result.access_token);
        console.log(sessionStorage.getItem("authToken"))
        // Set the user in context (you can adjust the user data as needed)
        login({ username: data.username, user_id: result.user_id }); // Store the username or any relevant user data

        navigate("/"); // Redirect to dashboard or home
      } else {
        const error = await response.json();
        console.error("Login failed:", error);
        // Handle errors (e.g., show error message)
      }
    } catch (error) {
      console.error("Error logging in:", error);
    }
  };

  const handleRegisterSubmit = async (data) => {
    try {
      const response = await fetch("http://localhost:8000/register", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(data),
      });

      if (response.ok) {
        const result = await response.json();
        console.log("Registration successful:", result);

        // Set the user in context after registration
        login({ username: data.username }); // Store the username or any relevant user data

        navigate("/"); // Redirect to dashboard or home
      } else {
        const error = await response.json();
        console.error("Registration failed:", error);
        // Handle errors (e.g., show error message)
      }
    } catch (error) {
      console.error("Error registering:", error);
    }
  };

  return (
    <Box display="flex" flexDirection="column" alignItems="center" mt={5}>
      {isLogin ? <Login onSubmit={handleLoginSubmit} /> : <Register onSubmit={handleRegisterSubmit} />}
      <Button onClick={toggleAuthMode} sx={{ mt: 2 }}>
        {isLogin ? "Don't have an account? Register" : "Already have an account? Login"}
      </Button>
    </Box>
  );
};

export default AuthPage;
