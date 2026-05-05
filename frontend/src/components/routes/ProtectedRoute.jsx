// src/components/ProtectedRoute.js
import React from 'react';
import { Navigate } from 'react-router-dom';
import { useUser } from '../../context/UserContext';

const ProtectedRoute = ({ children }) => {
  const { user } = useUser();

  return user ? children : <Navigate to="/auth" />;
};

export default ProtectedRoute;
