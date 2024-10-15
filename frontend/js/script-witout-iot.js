const ctx = document.getElementById('myChart').getContext('2d');

// Initialize Chart.js line chart
const myChart = new Chart(ctx, {
    type: 'line',
    data: {
        labels: [], // Start with an empty labels array
        datasets: [{
            label: 'Random Data',
            data: [], // Start with an empty data array
            borderColor: 'steelblue',
            backgroundColor: 'rgba(70,130,180,0.2)',
            borderWidth: 2,
            fill: true,
            tension: 0.1
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
            x: {
                title: {
                    display: true,
                    text: 'Data Points'
                },
                ticks: {
                    autoSkip: false, // Disable automatic skipping of ticks to show all labels
                    maxRotation: 90, // Rotate labels if they overlap
                    minRotation: 45 // Minimum rotation for better visibility
                },
                grid: {
                    drawOnChartArea: false // Hide grid lines for a cleaner look
                }
            },
            y: {
                title: {
                    display: true,
                    text: 'Value'
                },
                beginAtZero: true,
                suggestedMax: 100
            }
        },
        plugins: {
            zoom: {
                pan: {
                    enabled: true,
                    mode: 'x'
                },
                zoom: {
                    enabled: true,
                    mode: 'x'
                }
            }
        }
    }
});

let socket; // WebSocket variable

const startButton = document.getElementById("startButton");

startButton.addEventListener("click", () => {
    // Disable the button after clicking
    startButton.disabled = true;
    startButton.textContent = "Data Stream Started";

    // Initialize WebSocket connection
    socket = new WebSocket("ws://127.0.0.1:8000/ws");

    // Buffer for incoming data
    const dataBuffer = [];
    const bufferSize = 100; // Adjust the buffer size for averaging

    socket.onopen = function () {
        console.log("WebSocket connection established");
    };

    socket.onmessage = function (event) {
        console.log("Received data");
        const receivedData = event.data.match(/Random data: (\d+)/);

        // Ensure receivedData.value is a valid number
        if (receivedData && receivedData[1]) {
            const randomNumber = parseFloat(receivedData[1]);
            if (randomNumber !== null && !isNaN(randomNumber)) {
                // Add new data point to the buffer
                dataBuffer.push(randomNumber);

                // Check if we have enough data to calculate an average
                if (dataBuffer.length >= bufferSize) {
                    // Calculate average
                    const sum = dataBuffer.reduce((acc, value) => acc + value, 0);
                    const average = sum / bufferSize;

                    // Add average to the chart data
                    myChart.data.datasets[0].data.push(average);
                    myChart.data.labels.push(myChart.data.labels.length + 1); // Append a new label for each data point

                    // Update y-axis if necessary
                    const maxDataValue = Math.max(...myChart.data.datasets[0].data, 100);
                    myChart.options.scales.y.suggestedMax = maxDataValue > 100 ? maxDataValue : 100;

                    // Update the chart
                    myChart.update();

                    // Clear the buffer for the next set of data points
                    dataBuffer.length = 0; // Reset the buffer
                }
            } else {
                console.warn("Received invalid number:", receivedData.value);
            }
        };
    };

    socket.onclose = function () {
        console.log("WebSocket connection closed");
    };

    socket.onerror = function (error) {
        console.error("WebSocket error:", error);
    };
});

// Add event listener for maxForce slider
const maxForceSlider = document.getElementById("maxForce");
const maxForceValue = document.getElementById("maxForceValue");

maxForceSlider.addEventListener("input", () => {
    maxForceValue.textContent = maxForceSlider.value;
    console.log("sending max force");
    // Send the new max force to the backend via WebSocket
    const params = {
        parameter: "maxForce",
        value: parseInt(maxForceSlider.value)
    };
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(params));
    }
});
