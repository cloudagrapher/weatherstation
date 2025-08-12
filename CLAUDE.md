# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Setup

**Python Environment:**
- Uses Python 3.13 with a virtual environment at `.venv/`
- Activate with: `source .venv/bin/activate`  
- Dependencies listed in `requirements.txt`
- Install dependencies: `python -m pip install -r requirements.txt`

**Running Components:**
- Sensor service (weatherbox): `python sensor_to_influx.py`
- Dashboard service (masterbox): `python dashboard_masterbox.py`
- Production dashboard: `gunicorn --config gunicorn_config.py wsgi:application`
- Web dashboard accessible at: http://localhost:5000

## Architecture Overview

This is a distributed weather station system with two main components:

### Data Collection (weatherbox - Pi Zero W)
**Hardware Sensors:**
- DHT22 sensor (GPIO pin 4): Temperature and humidity readings every 2 seconds
- MPL115A2 sensor (I2C address 0x60): Barometric pressure with GPIO control (pins 17/27)
- Raspberry Pi GPIO interface for sensor control and data collection

**Sensor Service (`sensor_to_influx.py`):**
- `SensorLogger` class: High-frequency sensor readings (2-second interval)
- `MPL115A2` class: Hardware interface for barometric pressure sensor via I2C/GPIO
- Direct InfluxDB data transmission to masterbox
- Lightweight operation suitable for Pi Zero W resources

### Dashboard & Data Processing (masterbox - Pi 4)
**Core Components:**
- `WeatherDashboard` class: Web interface and real-time data display
- `WeatherDataService` class: InfluxDB data retrieval and processing layer
- Flask web server with SocketIO for real-time WebSocket communication
- Advanced weather prediction algorithms using pressure trends and atmospheric data

**Data Flow:**
- weatherbox sensors → InfluxDB (masterbox) → Dashboard (masterbox)
- Real-time WebSocket broadcasting to connected web clients
- Historical data analysis with configurable time windows
- Weather event tagging system for model improvement

**Web Interface:**
- Single-page dashboard (`templates/dashboard.html`) with real-time updates
- Chart.js for data visualization (24-hour trends, pressure history, 7-day view)
- User event tagging system with InfluxDB persistence
- Mobile-responsive design with touch-friendly controls

## Production Deployment

**Systemd Services:**
- **weatherbox**: `weather-sensors.service` runs `sensor_to_influx.py`
- **masterbox**: `weather-dashboard.service` runs gunicorn with `wsgi:application`
- Service configurations in `services/` directory
- Auto-restart enabled with 10-second delay on failure

**InfluxDB Configuration:**
- Running on masterbox at port 8086
- Configuration in `influxdb_config.py`
- Bucket: "sensors", Organization: "weatherbox"
- Weather data measurement: "weather", Events measurement: "weather_events"

## Key Development Commands

**Service Management (systemd):**
```bash
# Start services
sudo systemctl start weather-sensors.service    # on weatherbox
sudo systemctl start weather-dashboard.service  # on masterbox

# View logs  
sudo journalctl -u weather-sensors.service -f      # on weatherbox
sudo journalctl -u weather-dashboard.service -f    # on masterbox
```

**Development Testing:**
- Manual testing via web interface - no formal test framework
- Use "Take Reading Now" button for immediate data refresh
- Monitor WebSocket connection status in browser console
- InfluxDB data can be queried directly at http://masterbox:8086

## Key Features

**Advanced Weather Prediction:**
- Barometric pressure trend analysis with rate-of-change calculations
- Multi-factor predictions combining temperature, humidity, and pressure
- Confidence scoring for forecast accuracy
- Specialized algorithms for thunderstorms, fog, frost, and fire weather conditions

**Real-time Data Streaming:**
- WebSocket-based live updates to all connected clients
- 30-second periodic data refresh and broadcast
- User event tagging with immediate client notification
- Historical data visualization with multiple time ranges

**Hardware Integration Notes:**
- MPL115A2 pressure sensor requires calibration offset (-300 hPa)
- GPIO pins 17/27 control sensor power states (reset/shutdown)
- DHT22 readings validated for reasonable ranges (-40°C to 80°C, 0-100% humidity)
- I2C communication at address 0x60 for pressure sensor


- You can troubleshoot weatherbox directly with "ssh weatherbox@weatherbox.local"
- So, I'm currently talking to you from a Raspberry Pi 4 called masterbox. It was influxDB running on it at 8086. However, the code in this repository is actually running on a Pi Zero W called weatherbox. Because weatherbox's resources are quite limited, I cannot connect to it with my IDE so I code on masterbox and then transfer the code to weatherbox. What I want to do is run FrontEnd on masterbox and have weatherbox send it's readings to influxdb running on masterbox.