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
                    autoSkip: false,
                    maxRotation: 90,
                    minRotation: 45
                },
                grid: {
                    drawOnChartArea: false
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
let retryCount = 0;
const maxRetries = 10;
const bufferSize = 1000;  // Messages to buffer before processing
const dataBuffer = [];

const client_id = "ID123456789";

// Function to connect WebSocket and handle reconnections
function connectWebSocket() {
    socket = new WebSocket("ws://127.0.0.1:8000/ws");

    socket.onopen = function () {
        console.log("WebSocket connection established");
        retryCount = 0; // Reset retry count
        socket.send(JSON.stringify({ client_id: client_id }));
    };

    socket.onmessage = function (event) {
        console.log("Received data");
        const receivedData = event.data.match(/Random data: (\d+)/);

        if (receivedData && receivedData[1]) {
            const randomNumber = parseFloat(receivedData[1]);
            if (!isNaN(randomNumber)) {
                dataBuffer.push(randomNumber);  // Add new data point to buffer

                if (dataBuffer.length >= bufferSize) {
                    processBuffer(dataBuffer);  // Process if buffer is full
                }
            } else {
                console.warn("Received invalid number:", receivedData[1]);
            }
        }
    };

    socket.onclose = function () {
        console.log("WebSocket connection closed, retrying...");
        if (retryCount < maxRetries) {
            retryCount++;
            setTimeout(connectWebSocket, 2000);  // Retry connection after 2 seconds
        } else {
            console.error("Max retries reached, unable to reconnect.");
        }
    };

    socket.onerror = function (error) {
        console.error("WebSocket error:", error);
    };
}

// Automatically connect WebSocket when the page loads
window.onload = function () {
    connectWebSocket();
};

// Function to process the buffer and update the chart
function processBuffer(buffer) {
    console.log("Updating chart", buffer.length);

    // Calculate average
    const sum = buffer.reduce((acc, value) => acc + value, 0);
    const average = sum / buffer.length;

    // Add average to the chart data
    myChart.data.datasets[0].data.push(average);
    myChart.data.labels.push(myChart.data.labels.length + 1);

    // Update y-axis if necessary
    const maxDataValue = Math.max(...myChart.data.datasets[0].data, 100);
    myChart.options.scales.y.suggestedMax = maxDataValue > 100 ? maxDataValue : 100;

    // Update the chart
    myChart.update();

    // Clear the buffer for the next set of data points
    buffer.length = 0;
}

// Max Force Slider event listener
const maxForceSlider = document.getElementById("maxForce");
const maxForceValue = document.getElementById("maxForceValue");

maxForceSlider.addEventListener("input", () => {
    maxForceValue.textContent = maxForceSlider.value;
    console.log("Sending max force");

    const params = {
        parameter: "maxForce",
        value: parseInt(maxForceSlider.value)
    };

    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(params));  // Send max force value to server
    }
});

// Periodically process buffer if not full
setInterval(() => {
    if (dataBuffer.length > 0) {
        processBuffer(dataBuffer);
    }
}, 1000);  // Process every 1 second