// src/components/ProtectedRoute.js
// Guards routes so only authenticated users can access them.
// Waits for the session restore check to finish before deciding to redirect,
// preventing a false logout on page refresh.
import React from 'react';
import { Navigate } from 'react-router-dom';
import { useUser } from '../../context/UserContext';

const ProtectedRoute = ({ children }) => {
  const { user, isAuthLoading } = useUser();

  // Render nothing while the session restore is still in progress to avoid
  // a flash-redirect to /auth before the token has been validated.
  if (isAuthLoading) return null;

  return user ? children : <Navigate to="/auth" />;
};

export default ProtectedRoute;
