// Provides download handlers for exporting device data as HDF5 files.
// downloadDeviceData — legacy single-file export (all data for the user).
// downloadFolderData — per-folder export structured by curve index.
import { BACKEND_BASE_URL } from "../../../config/endpoints";

/**
 * useDeviceDataExport
 *
 * Returns download helpers that fetch HDF5 exports from the backend and
 * trigger browser file downloads.
 *
 * @param {string} [backendApiUrl] - Override the default API base URL.
 * @returns {{ downloadDeviceData: Function, downloadFolderData: Function }}
 */
const useDeviceDataExport = (backendApiUrl = BACKEND_BASE_URL) => {
  // Initiates a GET request to the legacy export endpoint and streams the response as a file download.
  const downloadDeviceData = async () => {
    try {
      // Reads the JWT stored at login so the export endpoint can scope data to this user.
      const token = sessionStorage.getItem("authToken");

      const response = await fetch(`${backendApiUrl}/api/export/device_data`, {
        headers: {
          // Sends the bearer token required by the now-authenticated export route.
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        // Prevent silent failure when the export endpoint is unavailable or unauthorized.
        throw new Error(`Failed to download the file. Status: ${response.status}`);
      }

      // Convert the response body to a Blob so a URL can be created for the anchor tag.
      const blob = await response.blob();

      // Creates a temporary object URL so the browser treats the blob as a downloadable file.
      const url = window.URL.createObjectURL(blob);

      // Creates a hidden anchor element to programmatically trigger the file download.
      const link = document.createElement("a");
      link.href = url;
      link.download = "device_data.hdf5";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (error) {
      // Surface download errors to the user rather than failing silently.
      console.error("Error downloading device data:", error);
      alert("Failed to download device data.");
    }
  };

  /**
   * Downloads the HDF5 export for a single folder, structured as
   * curve0/segment0/Force, curve0/segment0/Z, curve1/…, etc.
   * The filename is taken from the Content-Disposition response header
   * so it matches the folder name set by the user on the backend.
   *
   * @param {number} folderId - ID of the folder to export.
   */
  const downloadFolderData = async (folderId) => {
    try {
      // Reads the JWT stored at login so the export endpoint can scope data to this user.
      const token = sessionStorage.getItem("authToken");

      const response = await fetch(
        `${backendApiUrl}/api/export/folder/${folderId}`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (!response.ok) {
        // Extract the backend's detail message so the user sees the real reason.
        let detail = `Export failed (${response.status})`;
        try {
          const errBody = await response.json();
          if (errBody?.detail) detail = errBody.detail;
        } catch (_) {}
        throw new Error(detail);
      }

      // Extract the server-supplied filename from Content-Disposition so the
      // downloaded file matches the folder name (e.g. "Collagen A 2026-06-18.hdf5").
      const disposition = response.headers.get("Content-Disposition") ?? "";
      // Matches both quoted and unquoted filename values in the header.
      const filenameMatch = disposition.match(
        /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/
      );
      // Fall back to a generic name if the header is absent or unparseable.
      const filename = filenameMatch
        ? filenameMatch[1].replace(/['"]/g, "")
        : `folder_${folderId}.hdf5`;

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);

      // Programmatically click a hidden anchor to trigger the file-save dialog.
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      // Release the object URL to free browser memory after the download starts.
      window.URL.revokeObjectURL(url);
    } catch (error) {
      // Surface download errors to the user rather than failing silently.
      console.error("Error downloading folder data:", error);
      alert(error.message || "Failed to download folder data.");
    }
  };

  return { downloadDeviceData, downloadFolderData };
};

export default useDeviceDataExport;
