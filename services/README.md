# Services

## Weather Station Sensor Service (weatherbox - Pi Zero W)

The following represents the systemd service on the Pi Zero W for sensor data collection. This file is stored at `/etc/systemd/system/weather-sensors.service` on weatherbox.

```bash
[Unit]
Description=Weather Station Sensors to InfluxDB
After=network.target influxdb.service

[Service]
Type=simple
User=weatherbox
Group=weatherbox
WorkingDirectory=/home/weatherbox/weatherstation
ExecStart=/home/weatherbox/weatherstation/.venv/bin/python /home/weatherbox/weatherstation/sensor_to_influx.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Weather Dashboard Service (masterbox - Pi 4)

The following represents the systemd service on masterbox for the web dashboard. This file is stored at `/etc/systemd/system/weather-dashboard.service` on masterbox.

```bash
[Unit]
Description=Weather Station Dashboard
After=network.target influxdb.service

[Service]
Type=simple
User=masterbox
Group=masterbox
WorkingDirectory=/home/masterbox/weatherstation
ExecStart=/home/masterbox/weatherstation/.venv/bin/python /home/masterbox/weatherstation/dashboard_masterbox.py
Restart=always
RestartSec=10
Environment=FLASK_ENV=production

[Install]
WantedBy=multi-user.target
```

## Service Setup Instructions

### On weatherbox (Pi Zero W):
```bash
# Copy service file
sudo cp /home/weatherbox/weatherstation/services/weather-sensors.service /etc/systemd/system/

# Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable weather-sensors.service
sudo systemctl start weather-sensors.service

# Check status
sudo systemctl status weather-sensors.service
```

### On masterbox (Pi 4):
```bash
# Copy service file
sudo cp /home/masterbox/weatherstation/services/weather-dashboard.service /etc/systemd/system/

# Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable weather-dashboard.service
sudo systemctl start weather-dashboard.service

# Check status
sudo systemctl status weather-dashboard.service
```

## Service Management Commands

```bash
# Start service
sudo systemctl start weather-sensors.service    # on weatherbox
sudo systemctl start weather-dashboard.service  # on masterbox

# Stop service
sudo systemctl stop weather-sensors.service     # on weatherbox
sudo systemctl stop weather-dashboard.service   # on masterbox

# Restart service
sudo systemctl restart weather-sensors.service     # on weatherbox
sudo systemctl restart weather-dashboard.service   # on masterbox

# View logs
sudo journalctl -u weather-sensors.service -f      # on weatherbox
sudo journalctl -u weather-dashboard.service -f    # on masterbox
```
