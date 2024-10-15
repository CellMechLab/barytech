const ctx = document.getElementById('myChart').getContext('2d');

// Initialize Chart.js line chart
const myChart = new Chart(ctx, {
    type: 'line',
    data: {
        labels: Array.from({ length: 10 }, (_, i) => i + 1),
        datasets: [{
            label: 'Random Data',
            data: [],
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

    socket.onopen = function () {
        console.log("WebSocket connection established");
    };

    socket.onmessage = function (event) {
        console.log("Received data");
        let receivedData;
        try {
            receivedData = JSON.parse(event.data);
        } catch (error) {
            console.error("Error parsing JSON:", error);
            return;
        }

        const randomNumber = receivedData !== undefined ? parseFloat(receivedData) : null;

        if (randomNumber !== null && !isNaN(randomNumber)) {
            // Add new data point
            myChart.data.datasets[0].data.push(randomNumber);
            myChart.data.labels.push(myChart.data.labels.length + 1);

            // Keep only the latest 10 data points
            if (myChart.data.datasets[0].data.length > 10) {
                myChart.data.datasets[0].data.shift();
                myChart.data.labels.shift();
            }

            // Update y-axis if necessary
            const maxDataValue = Math.max(...myChart.data.datasets[0].data, 100);
            myChart.options.scales.y.suggestedMax = maxDataValue > 100 ? maxDataValue : 100;

            // Update the chart
            myChart.update();
        } else {
            console.warn("Received invalid number:", receivedData.value);
        }
    };

    socket.onclose = function () {
        console.log("WebSocket connection closed");
    };

    socket.onerror = function (error) {
        console.error("WebSocket error:", error);
    };
});
