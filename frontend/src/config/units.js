// Shared display units for telemetry stored as µm (displacement) and µN (force).

export const DISPLACEMENT_UNIT = process.env.REACT_APP_DISPLACEMENT_UNIT || "µm";
export const FORCE_UNIT = process.env.REACT_APP_FORCE_UNIT || "µN";

/** Format displacement already stored in micrometers. */
export const formatDisplacementMicrometers = (value, decimals = 3) => {
  const micrometers = Number(value);
  if (!Number.isFinite(micrometers)) return "—";
  const abs = Math.abs(micrometers);
  const text = abs >= 0.01 ? micrometers.toFixed(decimals) : micrometers.toExponential(2);
  return `${text} ${DISPLACEMENT_UNIT}`;
};

/** Format force already stored in micronewtons. */
export const formatForceMicronewtons = (value, decimals = 3) => {
  const micronewtons = Number(value);
  if (!Number.isFinite(micronewtons)) return "—";
  const abs = Math.abs(micronewtons);
  const text = abs >= 0.01 ? micronewtons.toFixed(decimals) : micronewtons.toExponential(2);
  return `${text} ${FORCE_UNIT}`;
};
