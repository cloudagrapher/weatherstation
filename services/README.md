# Services

The following represents the systemd service on the Pi Zero W. This file is stored at /etc/systemd/system/weather-station.service on the device.

```bash
[Unit]
Description=DHT22 Weather Station
After=network.target

[Service]
Type=simple
User=weatherbox
Group=weatherbox
WorkingDirectory=/home/weatherbox/weatherstation
ExecStart=/home/weatherbox/weatherstation/.venv/bin/python /home/weatherbox/weatherstation/dht22_weather_station.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```