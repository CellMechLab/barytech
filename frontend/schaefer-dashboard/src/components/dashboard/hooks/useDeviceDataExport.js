// Provides a single download handler for exporting raw device data as an HDF5 file.
// Isolates the export fetch logic from the Dashboard layout component.

// Reads the backend base URL once at module level for use in the export request.
const DEFAULT_API_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

/**
 * useDeviceDataExport
 *
 * Returns a downloadDeviceData function that fetches the HDF5 export from
 * /api/export/device_data and triggers a browser file download.
 *
 * @param {string} [backendApiUrl] - Override the default API base URL.
 * @returns {{ downloadDeviceData: Function }}
 */
const useDeviceDataExport = (backendApiUrl = DEFAULT_API_URL) => {
  // Initiates a GET request to the export endpoint and streams the response as a file download.
  const downloadDeviceData = async () => {
    try {
      const response = await fetch(`${backendApiUrl}/api/export/device_data`);

      if (!response.ok) {
        // Prevent silent failure when the export endpoint is unavailable.
        throw new Error("Failed to download the file.");
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

  return { downloadDeviceData };
};

export default useDeviceDataExport;
