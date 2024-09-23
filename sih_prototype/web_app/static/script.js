document.addEventListener('DOMContentLoaded', function () {
    // Initialize map
    const map = new maplibregl.Map({
        container: 'map-container',
        style: 'https://api.maptiler.com/maps/streets/style.json?key=39mJlgYyTu7B8GRTlJJ7',
        center: [78.9629, 20.5937], // Center of India
        zoom: 4
    });

    // Add zoom and rotation controls to the map.
    map.addControl(new maplibregl.NavigationControl());

    // Add India boundary
    map.on('load', function () {
        fetch('/static/india_boundary.geojson')
            .then(response => response.json())
            .then(data => {
                map.addSource('india-boundary', {
                    'type': 'geojson',
                    'data': data
                });

                map.addLayer({
                    'id': 'india-boundary-layer',
                    'type': 'line',
                    'source': 'india-boundary',
                    'paint': {
                        'line-color': '#000',
                        'line-width': 2
                    }
                });
            });
    });

    // Fetch DWLR data from the backend
    fetch('/get_dwlr_data')
        .then(response => response.json())
        .then(dwlrData => {
            // Add markers for each DWLR
            dwlrData.forEach(dwlr => {
                const el = document.createElement('div');
                el.className = 'marker';
                el.style.backgroundColor = getColorForWaterLevel(dwlr.water_level);
                el.style.width = '20px';
                el.style.height = '20px';
                el.style.borderRadius = '50%';

                new maplibregl.Marker(el)
                    .setLngLat([dwlr.lng, dwlr.lat])
                    .setPopup(new maplibregl.Popup().setHTML(`
                        <h3>DWLR at ${dwlr.lat.toFixed(4)}, ${dwlr.lng.toFixed(4)}</h3>
                        <p>Water Level: ${dwlr.water_level.toFixed(2)} m</p>
                        <p>Temperature: ${dwlr.temperature.toFixed(1)} °C</p>
                        <p>Rainfall: ${dwlr.rainfall.toFixed(1)} mm</p>
                        <p>pH: ${dwlr.ph.toFixed(2)}</p>
                        <p>Dissolved Oxygen: ${dwlr.dissolved_oxygen.toFixed(2)} mg/L</p>
                        <p>Last Updated: ${new Date(dwlr.timestamp).toLocaleString()}</p>
                    `))
                    .addTo(map);
            });
        })
        .catch(error => console.error('Error fetching DWLR data:', error));

    // Function to determine color based on water level
    function getColorForWaterLevel(level) {
        if (level < 2) return '#2ecc71'; // Low - Green
        if (level < 3) return '#f1c40f'; // Medium - Yellow
        if (level < 4) return '#e67e22'; // High - Orange
        return '#e74c3c'; // Very High - Red
    }

    // Handle form submission
    const telemetryForm = document.getElementById('telemetry-form');
    if (telemetryForm) {
        telemetryForm.addEventListener('submit', function (e) {
            e.preventDefault();

            const formData = new FormData(telemetryForm);
            const data = Object.fromEntries(formData.entries());

            // Convert numeric fields to numbers
            ['water_level', 'temperature', 'rainfall', 'ph', 'dissolved_oxygen', 'latitude', 'longitude'].forEach(field => {
                data[field] = parseFloat(data[field]);
            });

            fetch('/submit_telemetry', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(data),
            })
                .then(response => response.json())
                .then(result => {
                    const messageElement = document.getElementById('message');
                    messageElement.textContent = result.message;
                    messageElement.style.color = result.message.includes('Anomaly') ? 'red' : 'green';

                    // Clear form
                    telemetryForm.reset();

                    // Refresh map data
                    fetch('/get_dwlr_data')
                        .then(response => response.json())
                        .then(dwlrData => {
                            // Clear existing markers
                            document.querySelectorAll('.marker').forEach(el => el.remove());

                            // Add new markers
                            dwlrData.forEach(dwlr => {
                                const el = document.createElement('div');
                                el.className = 'marker';
                                el.style.backgroundColor = getColorForWaterLevel(dwlr.water_level);
                                el.style.width = '20px';
                                el.style.height = '20px';
                                el.style.borderRadius = '50%';

                                new maplibregl.Marker(el)
                                    .setLngLat([dwlr.lng, dwlr.lat])
                                    .setPopup(new maplibregl.Popup().setHTML(`
                                    <h3>DWLR at ${dwlr.lat.toFixed(4)}, ${dwlr.lng.toFixed(4)}</h3>
                                    <p>Water Level: ${dwlr.water_level.toFixed(2)} m</p>
                                    <p>Temperature: ${dwlr.temperature.toFixed(1)} °C</p>
                                    <p>Rainfall: ${dwlr.rainfall.toFixed(1)} mm</p>
                                    <p>pH: ${dwlr.ph.toFixed(2)}</p>
                                    <p>Dissolved Oxygen: ${dwlr.dissolved_oxygen.toFixed(2)} mg/L</p>
                                    <p>Last Updated: ${new Date(dwlr.timestamp).toLocaleString()}</p>
                                `))
                                    .addTo(map);
                            });
                        });
                })
                .catch(error => {
                    console.error('Error:', error);
                    const messageElement = document.getElementById('message');
                    messageElement.textContent = 'An error occurred while submitting data.';
                    messageElement.style.color = 'red';
                });
        });
    }
});