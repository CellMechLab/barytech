import React, { useContext } from 'react';
import { Box, Typography } from '@mui/material';
import { useTheme } from '@mui/material';
import { tokens } from '../../theme';
import { WebSocketContext } from './WebSocketProvider';
import { formatDisplacementMicrometers, formatForceMicronewtons } from '../../config/units';

const DataDisplay = () => {
  const theme = useTheme();
  const colors = tokens(theme.palette.mode);
  const { dataBuffer } = useContext(WebSocketContext);

  return (
    <Box>
      {dataBuffer.map((data, i) => (
        <Box
          key={`data-${i}`}
          display="flex"
          justifyContent="space-between"
          alignItems="center"
          borderBottom={`4px solid ${colors.primary[500]}`}
          p="15px"
        >
          <Box>
            <Typography color={colors.greenAccent[500]} variant="h5" fontWeight="600">
              Z: {formatDisplacementMicrometers(data.displacement)}
            </Typography>
            <Typography color={colors.grey[100]}>
              Force: {formatForceMicronewtons(data.force)}
            </Typography>
          </Box>
          <Box color={colors.grey[100]}>{new Date().toLocaleDateString()}</Box>
        </Box>
      ))}
    </Box>
  );
};

export default DataDisplay;
