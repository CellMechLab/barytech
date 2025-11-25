/**
 * Custom React hook for fetching aggregated device data efficiently.
 * 
 * This hook is optimized for chart visualization with large datasets.
 * It automatically handles data fetching, caching, and error handling.
 * 
 * Usage:
 *   const { data, loading, error, refetch } = useAggregatedDeviceData({
 *     deviceId: 'device123',
 *     intervalMinutes: 5,
 *     limit: 1000
 *   });
 */

import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';

/**
 * Hook for fetching aggregated device data for efficient chart rendering
 * 
 * @param {Object} config - Configuration object
 * @param {string} config.deviceId - Device ID to fetch data for
 * @param {number} config.intervalMinutes - Time bucket size in minutes (default: 5)
 * @param {number} config.limit - Maximum data points to return (default: 1000)
 * @param {boolean} config.enabled - Whether to auto-fetch on mount (default: true)
 * @returns {Object} { data, loading, error, refetch }
 */
export const useAggregatedDeviceData = ({
  deviceId,
  intervalMinutes = 5,
  limit = 1000,
  enabled = true
}) => {
  // State for data, loading, and error
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  
  const navigate = useNavigate();

  // Fetch function
  const fetchData = useCallback(async () => {
    if (!deviceId) {
      setError(new Error('Device ID is required'));
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const token = sessionStorage.getItem('authToken');
      if (!token) {
        toast.error('You are not logged in. Please log in to view data.', {
          style: { backgroundColor: 'red', color: 'white' },
        });
        navigate('/auth');
        return;
      }

      const response = await axios.get(
        'http://127.0.0.1:8000/api/device-data/aggregated',
        {
          params: {
            device_id: deviceId,
            interval_minutes: intervalMinutes,
            limit: limit,
          },
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      setData(response.data);
      setError(null);
    } catch (err) {
      if (err.response && err.response.status === 401) {
        toast.error('Session expired. Please log in again.', {
          style: { backgroundColor: 'red', color: 'white' },
        });
        sessionStorage.removeItem('authToken');
        navigate('/auth');
      } else {
        const errorMessage = err.response?.data?.detail || 'Failed to fetch aggregated data';
        setError(new Error(errorMessage));
        toast.error(errorMessage, {
          style: { backgroundColor: 'red', color: 'white' },
        });
      }
    } finally {
      setLoading(false);
    }
  }, [deviceId, intervalMinutes, limit, navigate]);

  // Auto-fetch on mount and when dependencies change
  useEffect(() => {
    if (enabled && deviceId) {
      fetchData();
    }
  }, [enabled, fetchData, deviceId]);

  // Return data and control functions
  return {
    data,
    loading,
    error,
    refetch: fetchData,
  };
};

/**
 * Hook for fetching paginated device data
 * 
 * @param {Object} config - Configuration object
 * @param {number} config.page - Page number (0-based)
 * @param {number} config.pageSize - Number of records per page
 * @param {string} config.deviceId - Optional device ID filter
 * @returns {Object} { data, pagination, loading, error, refetch }
 */
export const usePaginatedDeviceData = ({
  page = 0,
  pageSize = 100,
  deviceId = null
}) => {
  // State for data, pagination info, loading, and error
  const [data, setData] = useState([]);
  const [pagination, setPagination] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  
  const navigate = useNavigate();

  // Fetch function
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const token = sessionStorage.getItem('authToken');
      if (!token) {
        toast.error('You are not logged in. Please log in to view data.', {
          style: { backgroundColor: 'red', color: 'white' },
        });
        navigate('/auth');
        return;
      }

      const params = {
        page: page + 1, // Convert from 0-based to 1-based
        page_size: pageSize,
      };

      if (deviceId) {
        params.device_id = deviceId;
      }

      const response = await axios.get(
        'http://127.0.0.1:8000/api/device-data/paginated',
        {
          params,
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      setData(response.data.data);
      setPagination(response.data.pagination);
      setError(null);
    } catch (err) {
      if (err.response && err.response.status === 401) {
        toast.error('Session expired. Please log in again.', {
          style: { backgroundColor: 'red', color: 'white' },
        });
        sessionStorage.removeItem('authToken');
        navigate('/auth');
      } else {
        const errorMessage = err.response?.data?.detail || 'Failed to fetch device data';
        setError(new Error(errorMessage));
        toast.error(errorMessage, {
          style: { backgroundColor: 'red', color: 'white' },
        });
      }
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, deviceId, navigate]);

  // Auto-fetch when dependencies change
  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Return data and control functions
  return {
    data,
    pagination,
    loading,
    error,
    refetch: fetchData,
  };
};

export default useAggregatedDeviceData;






