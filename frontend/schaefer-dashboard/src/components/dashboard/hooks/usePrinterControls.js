// Encapsulates printer command state and consumes shared printer-status WebSocket data.
// Exposes a single hook so Dashboard components stay free of low-level fetch / WS logic.
import { useContext, useState } from "react";
import { WebSocketContext } from "../WebSocketProvider";

// Reads the backend base URL once at module level for use in every request.
const DEFAULT_API_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

/**
 * usePrinterControls
 *
 * Manages the full printer interaction surface:
 *  - Serial connect / disconnect
 *  - Motion commands (jog XYZ, home, extrude, retract, emergency stop)
 *  - Live status via /ws/printer WebSocket (position + temperatures)
 *
 * @param {string} [backendApiUrl] - Override the default API base URL.
 * @returns {object} Printer state values and command handler functions.
 */
const usePrinterControls = (backendApiUrl = DEFAULT_API_URL) => {
  // Reads the shared printer-status stream so multiple components stay in sync.
  const {
    printerPosition,
    bedTemperature,
    hotendTemperature,
  } = useContext(WebSocketContext);

  // Tracks whether a printer command HTTP request is currently in-flight.
  const [printerActionInProgress, setPrinterActionInProgress] = useState(false);

  // Stores the last human-readable status string shown in the controls card.
  const [printerActionStatus, setPrinterActionStatus] = useState("Idle");

  // Stores the jog step distance in mm applied to all axis movement, extrude, and retract actions.
  const [jogStep, setJogStep] = useState(1.0);

  // Tracks whether the Pi serial port is believed to be open (optimistic client state).
  const [printerConnected, setPrinterConnected] = useState(false);

  // ─── Generic command sender ───────────────────────────────────────────────

  /**
   * Sends a POST request to a printer endpoint and manages in-flight state.
   * Prevent duplicate submission when printerActionInProgress is true.
   *
   * @param {string} endpoint - Path relative to backendApiUrl (e.g. "/printer/move").
   * @param {object} body - JSON-serialisable request body.
   * @param {string} successMessage - Status string displayed on success.
   */
  const sendPrinterCommand = async (endpoint, body, successMessage) => {
    // Guard against duplicate command submission while a request is in-flight.
    if (printerActionInProgress) return;

    // Mark the request as in-flight so buttons are disabled during the call.
    setPrinterActionInProgress(true);

    // Inform the user that the command is being sent.
    setPrinterActionStatus("Sending...");

    try {
      const response = await fetch(`${backendApiUrl}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        throw new Error(`Printer command failed with status ${response.status}`);
      }

      // Reflect successful command completion in the status card.
      setPrinterActionStatus(successMessage);
    } catch (error) {
      // Prevent UI silence when the printer backend is unreachable or returns an error.
      setPrinterActionStatus("Command failed");
      console.error("Printer command error:", error);
    } finally {
      // Re-enable quick-control buttons after the request settles.
      setPrinterActionInProgress(false);
    }
  };

  // ─── Motion commands ──────────────────────────────────────────────────────

  /**
   * Jogs a single axis by the current jogStep distance.
   *
   * @param {"X"|"Y"|"Z"} axis - Axis to move.
   * @param {1|-1} direction - Positive or negative direction.
   */
  const handleJogAxis = async (axis, direction) => {
    // Z uses a slower feed rate to protect the bed; XY use faster travel speed.
    const feed = axis === "Z" ? 600 : 3000;
    await sendPrinterCommand(
      "/printer/move",
      { axis, distance: direction * jogStep, feed },
      `${axis}${direction > 0 ? "+" : "-"} ${jogStep} mm`
    );
  };

  // Sends G28 (home all axes) through the backend printer router.
  const handleHomePrinter = async () => {
    await sendPrinterCommand("/printer/home", {}, "Homed all axes");
  };

  // Triggers M112 firmware emergency stop — halts all motion immediately.
  const handleEmergencyStop = async () => {
    await sendPrinterCommand("/printer/emergency-stop", {}, "EMERGENCY STOP");
  };

  // Extrudes filament by the current jogStep distance.
  const handleExtrude = async () => {
    await sendPrinterCommand(
      "/printer/extrude",
      { distance: jogStep },
      `Extruded ${jogStep} mm`
    );
  };

  // Retracts filament by the current jogStep distance.
  const handleRetract = async () => {
    await sendPrinterCommand(
      "/printer/retract",
      { distance: jogStep },
      `Retracted ${jogStep} mm`
    );
  };

  // ─── Connection commands ──────────────────────────────────────────────────

  // Opens the Pi serial port so motion commands can be sent.
  const handleConnectPrinter = async () => {
    await sendPrinterCommand("/printer/connect", {}, "Printer connected");
    setPrinterConnected(true);
  };

  // Closes the Pi serial port — safe to call before powering off the printer.
  const handleDisconnectPrinter = async () => {
    await sendPrinterCommand("/printer/disconnect", {}, "Printer disconnected");
    setPrinterConnected(false);
  };

  return {
    // State
    printerActionInProgress,
    printerActionStatus,
    printerPosition,
    bedTemperature,
    hotendTemperature,
    jogStep,
    setJogStep,
    printerConnected,
    // Handlers
    handleJogAxis,
    handleHomePrinter,
    handleEmergencyStop,
    handleExtrude,
    handleRetract,
    handleConnectPrinter,
    handleDisconnectPrinter,
  };
};

export default usePrinterControls;
