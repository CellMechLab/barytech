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
  Divider,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  useTheme
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  Warning as WarningIcon,
  TrendingUp as TrendingUpIcon,
  Storage as StorageIcon,
  Wifi as WifiIcon,
  Speed as SpeedIcon,
  DataUsage as DataUsageIcon,
  Queue as QueueIcon,
  CloudQueue as CloudQueueIcon
} from '@mui/icons-material';

const API_BASE = 'http://localhost:8000';

const AdminPanel = () => {
  const theme = useTheme();
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
    <Box sx={{ p: 4, backgroundColor: '#f5f5f5', minHeight: '100vh' }}>
      {/* Header Section */}
      <Box sx={{ 
        backgroundColor: 'white', 
        p: 3, 
        borderRadius: 2, 
        mb: 4, 
        boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center' 
      }}>
        <Box>
          <Typography variant="h4" component="h1" sx={{ fontWeight: 600, color: '#1a237e' }}>
            🚀 IoT System Admin Dashboard
          </Typography>
          <Typography variant="body1" color="text.secondary" sx={{ mt: 1 }}>
            Real-time monitoring and system health overview
          </Typography>
        </Box>
        <Box display="flex" alignItems="center" gap={2}>
          <Button
            variant="contained"
            startIcon={<RefreshIcon />}
            onClick={refreshMetrics}
            disabled={loading}
            sx={{ 
              backgroundColor: '#1976d2',
              '&:hover': { backgroundColor: '#1565c0' }
            }}
          >
            Refresh
          </Button>
          {lastUpdate && (
            <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.875rem' }}>
              Last update: {lastUpdate.toLocaleTimeString()}
            </Typography>
          )}
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 4, borderRadius: 2 }}>
          {error}
        </Alert>
      )}

      {/* Top Level Metrics Cards */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        {/* System Health */}
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ 
            height: '100%', 
            borderRadius: 3, 
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
          }}>
            <CardContent sx={{ p: 3, color: 'white' }}>
              <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
                <Typography variant="h6" sx={{ fontWeight: 600 }}>
                  System Health
                </Typography>
                {health && getStatusIcon(health.status)}
              </Box>
              {health ? (
                <Chip
                  label={health.status.toUpperCase()}
                  color={getStatusColor(health.status)}
                  variant="filled"
                  sx={{ 
                    backgroundColor: 'rgba(255,255,255,0.2)', 
                    color: 'white',
                    fontWeight: 600
                  }}
                />
              ) : (
                <Typography>Loading...</Typography>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Pipeline Mode */}
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ 
            height: '100%', 
            borderRadius: 3, 
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)'
          }}>
            <CardContent sx={{ p: 3, color: 'white' }}>
              <Typography variant="h6" sx={{ fontWeight: 600, mb: 2 }}>
                Pipeline Mode
              </Typography>
              <Typography variant="h4" sx={{ fontWeight: 700, mb: 1 }}>
                {metrics?.production_mode || 'Unknown'}
              </Typography>
              <Typography variant="body2" sx={{ opacity: 0.9, mb: 2 }}>
                Current Mode
              </Typography>
              <Typography variant="h6" sx={{ fontWeight: 600 }}>
                {formatUptime(metrics?.elapsed_time || 0)}
              </Typography>
              <Typography variant="body2" sx={{ opacity: 0.9 }}>
                Uptime
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* Active Devices */}
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ 
            height: '100%', 
            borderRadius: 3, 
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            background: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)'
          }}>
            <CardContent sx={{ p: 3, color: 'white' }}>
              <Typography variant="h6" sx={{ fontWeight: 600, mb: 2 }}>
                Active Devices
              </Typography>
              <Typography variant="h4" sx={{ fontWeight: 700, mb: 1 }}>
                {formatNumber(metrics?.active_devices || 0)}
              </Typography>
              <Typography variant="body2" sx={{ opacity: 0.9, mb: 2 }}>
                Connected Devices
              </Typography>
              <Typography variant="h6" sx={{ fontWeight: 600 }}>
                {formatNumber(metrics?.device_health?.healthy_count || 0)}
              </Typography>
              <Typography variant="body2" sx={{ opacity: 0.9 }}>
                Healthy Devices
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* Total Data Points */}
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ 
            height: '100%', 
            borderRadius: 3, 
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            background: 'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)'
          }}>
            <CardContent sx={{ p: 3, color: 'white' }}>
              <Typography variant="h6" sx={{ fontWeight: 600, mb: 2 }}>
                Total Data Points
              </Typography>
              <Typography variant="h4" sx={{ fontWeight: 700, mb: 1 }}>
                {formatNumber(metrics?.total_data_points_produced || 0)}
              </Typography>
              <Typography variant="body2" sx={{ opacity: 0.9, mb: 2 }}>
                Processed
              </Typography>
              <Typography variant="h6" sx={{ fontWeight: 600 }}>
                {formatRate(metrics?.total_data_point_production_rate || 0)}/sec
              </Typography>
              <Typography variant="body2" sx={{ opacity: 0.9 }}>
                Current Rate
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* MQTT Layer Metrics */}
      <Card sx={{ mb: 4, borderRadius: 3, boxShadow: '0 4px 12px rgba(0,0,0,0.15)' }}>
        <CardContent sx={{ p: 4 }}>
          <Box display="flex" alignItems="center" gap={2} mb={3}>
            <WifiIcon sx={{ fontSize: 28, color: '#1976d2' }} />
            <Typography variant="h5" sx={{ fontWeight: 600, color: '#1a237e' }}>
              MQTT Layer Metrics
            </Typography>
          </Box>
          <Grid container spacing={4}>
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center" sx={{ p: 2, borderRadius: 2, backgroundColor: '#f8f9fa' }}>
                <Typography variant="h3" sx={{ fontWeight: 700, color: '#1976d2', mb: 1 }}>
                  {formatNumber(metrics?.mqtt_received || 0)}
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 600, color: '#424242', mb: 1 }}>
                  Frames Received
                </Typography>
                <Typography variant="h5" sx={{ color: '#666', fontWeight: 500 }}>
                  {formatRate(metrics?.mqtt_rate || 0)}/sec
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center" sx={{ p: 2, borderRadius: 2, backgroundColor: '#f8f9fa' }}>
                <Typography variant="h3" sx={{ fontWeight: 700, color: '#2e7d32', mb: 1 }}>
                  {formatNumber(metrics?.mqtt_data_points || 0)}
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 600, color: '#424242', mb: 1 }}>
                  Data Points
                </Typography>
                <Typography variant="h5" sx={{ color: '#666', fontWeight: 500 }}>
                  {formatRate(metrics?.mqtt_data_point_rate || 0)}/sec
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center" sx={{ p: 2, borderRadius: 2, backgroundColor: '#f8f9fa' }}>
                <Typography variant="h3" sx={{ fontWeight: 700, color: '#388e3c', mb: 1 }}>
                  {formatNumber(metrics?.mqtt_parsed || 0)}
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 600, color: '#424242', mb: 1 }}>
                  Successfully Parsed
                </Typography>
                <Typography variant="h5" sx={{ color: '#666', fontWeight: 500 }}>
                  {formatPercentage(metrics?.mqtt_parsed && metrics?.mqtt_received ? (metrics.mqtt_parsed / metrics.mqtt_received * 100) : 0)}
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center" sx={{ p: 2, borderRadius: 2, backgroundColor: '#f8f9fa' }}>
                <Typography variant="h3" sx={{ fontWeight: 700, color: '#d32f2f', mb: 1 }}>
                  {formatNumber(metrics?.mqtt_errors || 0)}
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 600, color: '#424242', mb: 1 }}>
                  Parse Errors
                </Typography>
                <Typography variant="h5" sx={{ color: '#666', fontWeight: 500 }}>
                  {formatNumber(metrics?.avg_data_points_per_mqtt || 0)}
                </Typography>
                <Typography variant="caption" sx={{ color: '#666' }}>
                  Avg Points/Frame
                </Typography>
              </Box>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Kafka Layer Metrics */}
      <Card sx={{ mb: 4, borderRadius: 3, boxShadow: '0 4px 12px rgba(0,0,0,0.15)' }}>
        <CardContent sx={{ p: 4 }}>
          <Box display="flex" alignItems="center" gap={2} mb={3}>
            <CloudQueueIcon sx={{ fontSize: 28, color: '#ff6f00' }} />
            <Typography variant="h5" sx={{ fontWeight: 600, color: '#1a237e' }}>
              Kafka Layer Metrics
            </Typography>
          </Box>
          <Grid container spacing={4}>
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center" sx={{ p: 2, borderRadius: 2, backgroundColor: '#fff3e0' }}>
                <Typography variant="h3" sx={{ fontWeight: 700, color: '#ff6f00', mb: 1 }}>
                  {formatNumber(metrics?.total_frames_produced || 0)}
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 600, color: '#424242', mb: 1 }}>
                  Total Frames Produced
                </Typography>
                <Typography variant="h5" sx={{ color: '#666', fontWeight: 500, mb: 1 }}>
                  {formatRate(metrics?.total_frame_production_rate || 0)}/sec
                </Typography>
                <Typography variant="caption" sx={{ color: '#666', display: 'block' }}>
                  {formatNumber(metrics?.frames_produced || 0)} per-device + {formatNumber(metrics?.kafka_first_frames_sent || 0)} kafka-first
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center" sx={{ p: 2, borderRadius: 2, backgroundColor: '#fff3e0' }}>
                <Typography variant="h3" sx={{ fontWeight: 700, color: '#ff6f00', mb: 1 }}>
                  {formatNumber(metrics?.total_data_points_produced || 0)}
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 600, color: '#424242', mb: 1 }}>
                  Total Data Points Produced
                </Typography>
                <Typography variant="h5" sx={{ color: '#666', fontWeight: 500, mb: 1 }}>
                  {formatRate(metrics?.total_data_point_production_rate || 0)}/sec
                </Typography>
                <Typography variant="caption" sx={{ color: '#666', display: 'block' }}>
                  {formatNumber(metrics?.data_points_produced || 0)} per-device + {formatNumber(metrics?.kafka_first_data_points_sent || 0)} kafka-first
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center" sx={{ p: 2, borderRadius: 2, backgroundColor: '#fff3e0' }}>
                <Typography variant="h3" sx={{ fontWeight: 700, color: '#ff6f00', mb: 1 }}>
                  {formatNumber(metrics?.frames_consumed || 0)}
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 600, color: '#424242', mb: 1 }}>
                  Frames Consumed
                </Typography>
                <Typography variant="h5" sx={{ color: '#666', fontWeight: 500 }}>
                  {formatRate(metrics?.frame_consumption_rate || 0)}/sec
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center" sx={{ p: 2, borderRadius: 2, backgroundColor: '#fff3e0' }}>
                <Typography variant="h3" sx={{ fontWeight: 700, color: '#ff6f00', mb: 1 }}>
                  {formatNumber(metrics?.data_points_consumed || 0)}
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 600, color: '#424242', mb: 1 }}>
                  Data Points Consumed
                </Typography>
                <Typography variant="h5" sx={{ color: '#666', fontWeight: 500, mb: 1 }}>
                  {formatRate(metrics?.data_point_consumption_rate || 0)}/sec
                </Typography>
                <Typography variant="caption" sx={{ color: '#666', display: 'block' }}>
                  Avg: {formatNumber(metrics?.avg_data_points_per_frame_consumed || 0)}/frame
                </Typography>
              </Box>
            </Grid>
          </Grid>
          
          {/* Kafka Production Mode */}
          <Box sx={{ mt: 3, p: 3, backgroundColor: '#fafafa', borderRadius: 2, border: '1px solid #e0e0e0' }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
              Production Mode: 
              <Chip 
                label={metrics?.production_mode || 'Unknown'} 
                color={metrics?.production_mode === 'kafka_first_only' ? 'success' : 
                       metrics?.production_mode === 'per_device_only' ? 'info' : 
                       metrics?.production_mode === 'both_active' ? 'warning' : 'default'}
                size="small"
                sx={{ ml: 1 }}
              />
            </Typography>
            {metrics?.kafka_first_stats && (
              <Typography variant="body2" color="text.secondary">
                Kafka-First Queues: Retry={formatNumber(metrics.kafka_first_stats.retry_queue_size || 0)}, 
                Overflow={formatNumber(metrics.kafka_first_stats.overflow_queue_size || 0)}
              </Typography>
            )}
          </Box>
        </CardContent>
      </Card>

      {/* Processing & Broadcasting Metrics */}
      <Card sx={{ mb: 4, borderRadius: 3, boxShadow: '0 4px 12px rgba(0,0,0,0.15)' }}>
        <CardContent sx={{ p: 4 }}>
          <Box display="flex" alignItems="center" gap={2} mb={3}>
            <SpeedIcon sx={{ fontSize: 28, color: '#7b1fa2' }} />
            <Typography variant="h5" sx={{ fontWeight: 600, color: '#1a237e' }}>
              Processing & Broadcasting Metrics
            </Typography>
          </Box>
          <Grid container spacing={4}>
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center" sx={{ p: 2, borderRadius: 2, backgroundColor: '#f3e5f5' }}>
                <Typography variant="h3" sx={{ fontWeight: 700, color: '#7b1fa2', mb: 1 }}>
                  {formatNumber(metrics?.total_messages_sent_to_frontend || 0)}
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 600, color: '#424242', mb: 1 }}>
                  Messages Sent to Frontend
                </Typography>
                <Typography variant="h5" sx={{ color: '#666', fontWeight: 500 }}>
                  {formatRate(metrics?.frontend_message_rate || 0)}/sec
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center" sx={{ p: 2, borderRadius: 2, backgroundColor: '#f3e5f5' }}>
                <Typography variant="h3" sx={{ fontWeight: 700, color: '#7b1fa2', mb: 1 }}>
                  {formatNumber(metrics?.total_messages_saved || 0)}
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 600, color: '#424242', mb: 1 }}>
                  Messages Saved to DB
                </Typography>
                <Typography variant="h5" sx={{ color: '#666', fontWeight: 500 }}>
                  {formatRate(metrics?.db_save_rate || 0)}/sec
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center" sx={{ p: 2, borderRadius: 2, backgroundColor: '#f3e5f5' }}>
                <Typography variant="h3" sx={{ fontWeight: 700, color: '#7b1fa2', mb: 1 }}>
                  {formatNumber(metrics?.total_messages_deduplicated || 0)}
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 600, color: '#424242', mb: 1 }}>
                  Messages Deduplicated
                </Typography>
                <Typography variant="h5" sx={{ color: '#666', fontWeight: 500 }}>
                  {formatPercentage(metrics?.deduplication_rate || 0)}
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center" sx={{ p: 2, borderRadius: 2, backgroundColor: '#f3e5f5' }}>
                <Typography variant="h3" sx={{ fontWeight: 700, color: '#7b1fa2', mb: 1 }}>
                  {formatNumber(metrics?.total_messages_batched || 0)}
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 600, color: '#424242', mb: 1 }}>
                  Messages Batched
                </Typography>
                <Typography variant="h5" sx={{ color: '#666', fontWeight: 500 }}>
                  {formatNumber(metrics?.avg_batch_size || 0)}
                </Typography>
                <Typography variant="caption" sx={{ color: '#666' }}>
                  Avg Batch Size
                </Typography>
              </Box>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Queue & Buffer Metrics */}
      <Card sx={{ mb: 4, borderRadius: 3, boxShadow: '0 4px 12px rgba(0,0,0,0.15)' }}>
        <CardContent sx={{ p: 4 }}>
          <Box display="flex" alignItems="center" gap={2} mb={3}>
            <QueueIcon sx={{ fontSize: 28, color: '#c62828' }} />
            <Typography variant="h5" sx={{ fontWeight: 600, color: '#1a237e' }}>
              Queue & Buffer Metrics
            </Typography>
          </Box>
          <Grid container spacing={4}>
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center" sx={{ p: 2, borderRadius: 2, backgroundColor: '#ffebee' }}>
                <Typography variant="h3" sx={{ fontWeight: 700, color: '#c62828', mb: 1 }}>
                  {formatNumber(metrics?.total_queue_size || 0)}
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 600, color: '#424242', mb: 1 }}>
                  Total Queue Size
                </Typography>
                <Typography variant="h5" sx={{ color: '#666', fontWeight: 500 }}>
                  {formatPercentage(metrics?.queue_utilization || 0)}
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center" sx={{ p: 2, borderRadius: 2, backgroundColor: '#ffebee' }}>
                <Typography variant="h3" sx={{ fontWeight: 700, color: '#c62828', mb: 1 }}>
                  {formatNumber(metrics?.total_buffer_size || 0)}
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 600, color: '#424242', mb: 1 }}>
                  Total Buffer Size
                </Typography>
                <Typography variant="h5" sx={{ color: '#666', fontWeight: 500 }}>
                  {formatPercentage(metrics?.buffer_utilization || 0)}
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center" sx={{ p: 2, borderRadius: 2, backgroundColor: '#ffebee' }}>
                <Typography variant="h3" sx={{ fontWeight: 700, color: '#c62828', mb: 1 }}>
                  {formatNumber(metrics?.total_retry_queue_size || 0)}
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 600, color: '#424242', mb: 1 }}>
                  Total Retry Queue Size
                </Typography>
                <Typography variant="h5" sx={{ color: '#666', fontWeight: 500 }}>
                  {formatNumber(metrics?.total_overflow_queue_size || 0)}
                </Typography>
                <Typography variant="caption" sx={{ color: '#666' }}>
                  Overflow Queue
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center" sx={{ p: 2, borderRadius: 2, backgroundColor: '#ffebee' }}>
                <Typography variant="h3" sx={{ fontWeight: 700, color: '#c62828', mb: 1 }}>
                  {formatNumber(metrics?.total_dropped_messages || 0)}
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 600, color: '#424242', mb: 1 }}>
                  Total Dropped Messages
                </Typography>
                <Typography variant="h5" sx={{ color: '#666', fontWeight: 500 }}>
                  {formatPercentage(metrics?.drop_rate || 0)}
                </Typography>
              </Box>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Performance & Latency Metrics */}
      <Card sx={{ mb: 4, borderRadius: 3, boxShadow: '0 4px 12px rgba(0,0,0,0.15)' }}>
        <CardContent sx={{ p: 4 }}>
          <Box display="flex" alignItems="center" gap={2} mb={3}>
            <TrendingUpIcon sx={{ fontSize: 28, color: '#2e7d32' }} />
            <Typography variant="h5" sx={{ fontWeight: 600, color: '#1a237e' }}>
              Performance & Latency Metrics
            </Typography>
          </Box>
          <Grid container spacing={4}>
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center" sx={{ p: 2, borderRadius: 2, backgroundColor: '#e8f5e8' }}>
                <Typography variant="h3" sx={{ fontWeight: 700, color: '#2e7d32', mb: 1 }}>
                  {formatNumber(metrics?.avg_processing_time || 0)}
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 600, color: '#424242', mb: 1 }}>
                  Avg Processing Time
                </Typography>
                <Typography variant="h5" sx={{ color: '#666', fontWeight: 500 }}>
                  ms
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center" sx={{ p: 2, borderRadius: 2, backgroundColor: '#e8f5e8' }}>
                <Typography variant="h3" sx={{ fontWeight: 700, color: '#2e7d32', mb: 1 }}>
                  {formatNumber(metrics?.avg_latency || 0)}
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 600, color: '#424242', mb: 1 }}>
                  Avg Latency
                </Typography>
                <Typography variant="h5" sx={{ color: '#666', fontWeight: 500 }}>
                  ms
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center" sx={{ p: 2, borderRadius: 2, backgroundColor: '#e8f5e8' }}>
                <Typography variant="h3" sx={{ fontWeight: 700, color: '#2e7d32', mb: 1 }}>
                  {formatNumber(metrics?.throughput || 0)}
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 600, color: '#424242', mb: 1 }}>
                  Throughput
                </Typography>
                <Typography variant="h5" sx={{ color: '#666', fontWeight: 500 }}>
                  msg/sec
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center" sx={{ p: 2, borderRadius: 2, backgroundColor: '#e8f5e8' }}>
                <Typography variant="h3" sx={{ fontWeight: 700, color: '#2e7d32', mb: 1 }}>
                  {formatNumber(metrics?.cpu_usage || 0)}
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 600, color: '#424242', mb: 1 }}>
                  CPU Usage
                </Typography>
                <Typography variant="h5" sx={{ color: '#666', fontWeight: 500 }}>
                  %
                </Typography>
              </Box>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Device Health Table */}
      {metrics?.device_health && (
        <Card sx={{ borderRadius: 3, boxShadow: '0 4px 12px rgba(0,0,0,0.15)' }}>
          <CardContent sx={{ p: 4 }}>
            <Box display="flex" alignItems="center" gap={2} mb={3}>
              <StorageIcon sx={{ fontSize: 28, color: '#1565c0' }} />
              <Typography variant="h5" sx={{ fontWeight: 600, color: '#1a237e' }}>
                Device Health Overview
              </Typography>
            </Box>
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
                    <TableCell sx={{ fontWeight: 600 }}>Device ID</TableCell>
                    <TableCell sx={{ fontWeight: 600 }}>Status</TableCell>
                    <TableCell sx={{ fontWeight: 600 }}>Last Seen</TableCell>
                    <TableCell sx={{ fontWeight: 600 }}>Message Count</TableCell>
                    <TableCell sx={{ fontWeight: 600 }}>Error Count</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {Object.entries(metrics.device_health).map(([deviceId, health]) => (
                    <TableRow key={deviceId}>
                      <TableCell sx={{ fontWeight: 500 }}>{deviceId}</TableCell>
                      <TableCell>
                        <Chip
                          label={health.status || 'Unknown'}
                          color={getStatusColor(health.status)}
                          size="small"
                        />
                      </TableCell>
                      <TableCell>{formatUptime(health.last_seen || 0)}</TableCell>
                      <TableCell>{formatNumber(health.message_count || 0)}</TableCell>
                      <TableCell>{formatNumber(health.error_count || 0)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      )}
    </Box>
  );
};

export default AdminPanel;
