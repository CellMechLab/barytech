/**
 * Example component showing how to use aggregated device data for efficient chart rendering.
 * 
 * This component demonstrates:
 * - Using the useAggregatedDeviceData hook
 * - Rendering charts with large datasets efficiently
 * - Configurable aggregation intervals
 * - Responsive chart layout
 * 
 * Usage:
 *   <AggregatedChart deviceId="device123" />
 */

import React, { useState, useMemo } from 'react';
import { Box, FormControl, InputLabel, Select, MenuItem, CircularProgress, Typography } from '@mui/material';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { useAggregatedDeviceData } from '../../hooks/useAggregatedDeviceData';
import { useTheme } from '@mui/material';
import { tokens } from '../../theme';

/**
 * Chart component for displaying aggregated device data
 */
const AggregatedChart = ({ deviceId }) => {
  const theme = useTheme();
  const colors = tokens(theme.palette.mode);
  
  // State for aggregation interval selection
  const [intervalMinutes, setIntervalMinutes] = useState(5);
  const [limit, setLimit] = useState(1000);
  
  // Fetch aggregated data using custom hook
  const { data, loading, error, refetch } = useAggregatedDeviceData({
    deviceId,
    intervalMinutes,
    limit,
    enabled: !!deviceId, // Only fetch if deviceId is provided
  });

  // Format data for chart rendering
  const chartData = useMemo(() => {
    if (!data || !data.data) return [];
    
    return data.data.map((point) => ({
      // Format timestamp for display
      timestamp: new Date(point.timestamp).toLocaleString('en-GB', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      }),
      // Convert values to numbers for chart
      avgDisplacement: parseFloat(point.avg_displacement) || 0,
      minDisplacement: parseFloat(point.min_displacement) || 0,
      maxDisplacement: parseFloat(point.max_displacement) || 0,
      avgForce: parseFloat(point.avg_force) || 0,
      minForce: parseFloat(point.min_force) || 0,
      maxForce: parseFloat(point.max_force) || 0,
      sampleCount: point.sample_count,
    }));
  }, [data]);

  // Handle interval change
  const handleIntervalChange = (event) => {
    setIntervalMinutes(event.target.value);
  };

  // Handle limit change
  const handleLimitChange = (event) => {
    setLimit(event.target.value);
  };

  // Render loading state
  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" height="400px">
        <CircularProgress />
      </Box>
    );
  }

  // Render error state
  if (error) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" height="400px">
        <Typography color="error">Error loading data: {error.message}</Typography>
      </Box>
    );
  }

  // Render no data state
  if (!deviceId) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" height="400px">
        <Typography>Please select a device to view chart</Typography>
      </Box>
    );
  }

  return (
    <Box>
      {/* Controls for aggregation settings */}
      <Box display="flex" gap={2} mb={2}>
        <FormControl sx={{ minWidth: 200 }}>
          <InputLabel>Aggregation Interval</InputLabel>
          <Select
            value={intervalMinutes}
            label="Aggregation Interval"
            onChange={handleIntervalChange}
          >
            <MenuItem value={1}>1 minute</MenuItem>
            <MenuItem value={5}>5 minutes</MenuItem>
            <MenuItem value={10}>10 minutes</MenuItem>
            <MenuItem value={30}>30 minutes</MenuItem>
            <MenuItem value={60}>1 hour</MenuItem>
          </Select>
        </FormControl>

        <FormControl sx={{ minWidth: 200 }}>
          <InputLabel>Max Data Points</InputLabel>
          <Select
            value={limit}
            label="Max Data Points"
            onChange={handleLimitChange}
          >
            <MenuItem value={500}>500 points</MenuItem>
            <MenuItem value={1000}>1,000 points</MenuItem>
            <MenuItem value={2000}>2,000 points</MenuItem>
            <MenuItem value={5000}>5,000 points</MenuItem>
          </Select>
        </FormControl>

        {data && (
          <Box display="flex" alignItems="center" ml={2}>
            <Typography variant="body2" color={colors.grey[100]}>
              Showing {data.data_points} data points
              {data.data_points > 0 && ` (${intervalMinutes} min intervals)`}
            </Typography>
          </Box>
        )}
      </Box>

      {/* Displacement Chart */}
      <Box mb={4}>
        <Typography variant="h6" mb={2}>
          Displacement Over Time
        </Typography>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke={colors.grey[700]} />
            <XAxis 
              dataKey="timestamp" 
              stroke={colors.grey[100]}
              tick={{ fill: colors.grey[100] }}
            />
            <YAxis 
              stroke={colors.grey[100]}
              tick={{ fill: colors.grey[100] }}
              label={{ value: 'Displacement (mm)', angle: -90, position: 'insideLeft', fill: colors.grey[100] }}
            />
            <Tooltip 
              contentStyle={{ 
                backgroundColor: colors.primary[400], 
                border: `1px solid ${colors.grey[700]}` 
              }}
            />
            <Legend />
            <Line 
              type="monotone" 
              dataKey="avgDisplacement" 
              stroke={colors.greenAccent[500]} 
              name="Average"
              dot={false}
            />
            <Line 
              type="monotone" 
              dataKey="minDisplacement" 
              stroke={colors.blueAccent[500]} 
              name="Min"
              dot={false}
              strokeDasharray="5 5"
            />
            <Line 
              type="monotone" 
              dataKey="maxDisplacement" 
              stroke={colors.redAccent[500]} 
              name="Max"
              dot={false}
              strokeDasharray="5 5"
            />
          </LineChart>
        </ResponsiveContainer>
      </Box>

      {/* Force Chart */}
      <Box>
        <Typography variant="h6" mb={2}>
          Force Over Time
        </Typography>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke={colors.grey[700]} />
            <XAxis 
              dataKey="timestamp" 
              stroke={colors.grey[100]}
              tick={{ fill: colors.grey[100] }}
            />
            <YAxis 
              stroke={colors.grey[100]}
              tick={{ fill: colors.grey[100] }}
              label={{ value: 'Force (N)', angle: -90, position: 'insideLeft', fill: colors.grey[100] }}
            />
            <Tooltip 
              contentStyle={{ 
                backgroundColor: colors.primary[400], 
                border: `1px solid ${colors.grey[700]}` 
              }}
            />
            <Legend />
            <Line 
              type="monotone" 
              dataKey="avgForce" 
              stroke={colors.greenAccent[500]} 
              name="Average"
              dot={false}
            />
            <Line 
              type="monotone" 
              dataKey="minForce" 
              stroke={colors.blueAccent[500]} 
              name="Min"
              dot={false}
              strokeDasharray="5 5"
            />
            <Line 
              type="monotone" 
              dataKey="maxForce" 
              stroke={colors.redAccent[500]} 
              name="Max"
              dot={false}
              strokeDasharray="5 5"
            />
          </LineChart>
        </ResponsiveContainer>
      </Box>
    </Box>
  );
};

export default AggregatedChart;






