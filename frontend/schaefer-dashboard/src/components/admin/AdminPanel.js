import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  Button,
  CircularProgress,
  Alert,
  Chip,
  Paper,
  Divider
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  Warning as WarningIcon,
  TrendingUp as TrendingUpIcon,
  Storage as StorageIcon,
  Wifi as WifiIcon,
  Speed as SpeedIcon
} from '@mui/icons-material';

const API_BASE = 'http://localhost:8000';

const AdminPanel = () => {
  const [metrics, setMetrics] = useState(null);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);

  const fetchMetrics = async () => {
    try {
      const response = await fetch(`${API_BASE}/monitoring/stats`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Error fetching metrics:', error);
      throw new Error('Failed to fetch metrics. Make sure the backend is running.');
    }
  };

  const fetchHealth = async () => {
    try {
      const response = await fetch(`${API_BASE}/monitoring/health`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Error fetching health:', error);
      return null;
    }
  };

  const refreshMetrics = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const [metricsData, healthData] = await Promise.all([
        fetchMetrics(),
        fetchHealth()
      ]);
      
      setMetrics(metricsData);
      setHealth(healthData);
      setLastUpdate(new Date());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshMetrics();
    
    // Auto-refresh every 5 seconds
    const interval = setInterval(refreshMetrics, 5000);
    return () => clearInterval(interval);
  }, []);

  const formatNumber = (num) => {
    if (num === null || num === undefined) return '-';
    return num.toLocaleString();
  };

  const formatRate = (rate) => {
    if (rate === null || rate === undefined) return '-';
    return rate.toFixed(1);
  };

  const formatPercentage = (rate) => {
    if (rate === null || rate === undefined) return '-';
    return `${rate.toFixed(1)}%`;
  };

  const formatUptime = (seconds) => {
    if (!seconds) return '-';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    return `${hours}h ${minutes}m ${secs}s`;
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'healthy': return 'success';
      case 'degraded': return 'warning';
      case 'error': return 'error';
      default: return 'default';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'healthy': return <CheckCircleIcon />;
      case 'degraded': return <WarningIcon />;
      case 'error': return <ErrorIcon />;
      default: return <ErrorIcon />;
    }
  };

  if (loading && !metrics) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4" component="h1" gutterBottom>
          🚀 MQTT System Admin Panel
        </Typography>
        <Box display="flex" alignItems="center" gap={2}>
          <Button
            variant="contained"
            startIcon={<RefreshIcon />}
            onClick={refreshMetrics}
            disabled={loading}
          >
            Refresh Metrics
          </Button>
          {lastUpdate && (
            <Typography variant="caption" color="text.secondary">
              Last update: {lastUpdate.toLocaleTimeString()}
            </Typography>
          )}
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      <Grid container spacing={3}>
        {/* System Health */}
        <Grid item xs={12} md={6} lg={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                System Health
              </Typography>
              {health ? (
                <Box display="flex" alignItems="center" gap={1}>
                  <Chip
                    icon={getStatusIcon(health.status)}
                    label={health.status.toUpperCase()}
                    color={getStatusColor(health.status)}
                    variant="outlined"
                  />
                </Box>
              ) : (
                <Typography color="text.secondary">Loading...</Typography>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* MQTT Processing */}
        <Grid item xs={12} md={6} lg={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                MQTT Processing
              </Typography>
              <Typography variant="h4" color="primary">
                {formatNumber(metrics?.mqtt_received || 0)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Messages Received
              </Typography>
              <Typography variant="h5" color="secondary" sx={{ mt: 1 }}>
                {formatRate(metrics?.mqtt_rate || 0)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Messages/sec
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* Message Processing */}
        <Grid item xs={12} md={6} lg={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Message Processing
              </Typography>
              <Typography variant="h4" color="primary">
                {formatRate(metrics?.processing_rate || 0)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Processing Rate (msg/sec)
              </Typography>
              <Typography variant="h5" color="secondary" sx={{ mt: 1 }}>
                {formatPercentage(health?.parsing_success_rate || 0)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Parsing Success Rate
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* WebSocket Broadcasting */}
        <Grid item xs={12} md={6} lg={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                WebSocket Broadcasting
              </Typography>
              <Typography variant="h4" color="primary">
                {formatRate(metrics?.broadcast_rate || 0)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Broadcast Rate (msg/sec)
              </Typography>
              <Typography variant="h5" color="secondary" sx={{ mt: 1 }}>
                {formatNumber(metrics?.ws_connections || 0)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Active Connections
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* Database Operations */}
        <Grid item xs={12} md={6} lg={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Database Operations
              </Typography>
              <Typography variant="h4" color="primary">
                {formatRate(metrics?.db_rate || 0)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                DB Write Rate (msg/sec)
              </Typography>
              <Typography variant="h5" color="secondary" sx={{ mt: 1 }}>
                {formatNumber(metrics?.db_saved || 0)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Total Saved
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* System Information */}
        <Grid item xs={12} md={6} lg={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                System Information
              </Typography>
              <Typography variant="h4" color="primary">
                {formatUptime(metrics?.elapsed_time || 0)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Uptime
              </Typography>
              <Typography variant="h5" color="secondary" sx={{ mt: 1 }}>
                {formatNumber(metrics?.active_devices || 0)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Active Devices
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Message Flow Visualization */}
      <Paper sx={{ p: 3, mt: 3 }}>
        <Typography variant="h6" gutterBottom>
          Real-time Message Flow
        </Typography>
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6} md={2.4}>
            <Box
              sx={{
                bgcolor: '#e3f2fd',
                p: 2,
                borderRadius: 1,
                textAlign: 'center'
              }}
            >
              <Typography variant="h4" color="#1976d2" fontWeight="bold">
                {formatNumber(metrics?.mqtt_received || 0)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                MQTT Received
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={12} sm={6} md={2.4}>
            <Box
              sx={{
                bgcolor: '#f3e5f5',
                p: 2,
                borderRadius: 1,
                textAlign: 'center'
              }}
            >
              <Typography variant="h4" color="#7b1fa2" fontWeight="bold">
                {formatNumber(metrics?.mqtt_parsed || 0)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Parsed
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={12} sm={6} md={2.4}>
            <Box
              sx={{
                bgcolor: '#e8f5e8',
                p: 2,
                borderRadius: 1,
                textAlign: 'center'
              }}
            >
              <Typography variant="h4" color="#388e3c" fontWeight="bold">
                {formatNumber(metrics?.device_processed || 0)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Processed
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={12} sm={6} md={2.4}>
            <Box
              sx={{
                bgcolor: '#fff3e0',
                p: 2,
                borderRadius: 1,
                textAlign: 'center'
              }}
            >
              <Typography variant="h4" color="#f57c00" fontWeight="bold">
                {formatNumber(metrics?.broadcast_sent || 0)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Broadcast
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={12} sm={6} md={2.4}>
            <Box
              sx={{
                bgcolor: '#fce4ec',
                p: 2,
                borderRadius: 1,
                textAlign: 'center'
              }}
            >
              <Typography variant="h4" color="#c2185b" fontWeight="bold">
                {formatNumber(metrics?.db_saved || 0)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Saved to DB
              </Typography>
            </Box>
          </Grid>
        </Grid>
      </Paper>
    </Box>
  );
};

export default AdminPanel;
