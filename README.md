# Weather Station System

A distributed weather monitoring system built with Raspberry Pi devices, featuring real-time sensor data collection, web dashboard, and advanced weather prediction algorithms.

## Architecture

### Hardware Setup
- **weatherbox** (Pi Zero W): Data collection unit with sensors
- **masterbox** (Pi 4): Dashboard server and data storage

### System Components
- **Data Collection**: DHT22 (temperature/humidity) + MPL115A2 (barometric pressure)
- **Database**: InfluxDB running on masterbox
- **Dashboard**: Flask web interface with real-time updates
- **Communication**: WiFi network connection between devices

## Quick Start

### Prerequisites
- Python 3.13 with virtual environment
- InfluxDB 2.x running on masterbox
- Systemd for service management

### Installation

1. **Clone and setup environment:**
   ```bash
   git clone <repository>
   cd weatherstation
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure InfluxDB connection:**
   - Edit `config/influxdb_config.py` with your settings
   - Ensure InfluxDB is running on masterbox:8086

3. **Deploy services:**
   ```bash
   # On masterbox (dashboard)
   sudo cp services/weather-dashboard.service /etc/systemd/system/
   sudo systemctl enable weather-dashboard.service
   sudo systemctl start weather-dashboard.service
   
   # On weatherbox (sensors) 
   sudo cp services/weather-sensors.service /etc/systemd/system/
   sudo systemctl enable weather-sensors.service
   sudo systemctl start weather-sensors.service
   ```

4. **Access dashboard:**
   - Open browser to http://masterbox:5000 or http://localhost:5000

## Directory Structure

```
weatherstation/
├── src/                          # Core application code
│   ├── sensor_to_influx.py      # Sensor data collection (weatherbox)
│   ├── dashboard_masterbox.py   # Web dashboard (masterbox)
│   ├── weather_api_service.py   # Weather API integration
│   └── influxdb_data_service.py # Database access layer
├── config/                       # Configuration files
│   ├── influxdb_config.py       # InfluxDB connection settings
│   └── gunicorn_config.py       # Production server config
├── templates/                    # HTML templates
│   ├── dashboard.html           # Main dashboard interface
│   └── analysis.html           # Data analysis page
├── services/                     # Systemd service definitions
│   ├── weather-dashboard.service
│   └── weather-sensors.service
├── scripts/                      # Utility scripts
│   ├── data_maintenance/        # Database maintenance tools
│   └── testing/                 # Test scripts
├── wheels/                      # Python package wheels
├── wsgi.py                      # WSGI entry point
└── requirements.txt             # Python dependencies
```

## Core Features

### Real-time Monitoring
- **Sensor Readings**: Temperature, humidity, barometric pressure every 2 seconds
- **Live Dashboard**: WebSocket-based real-time updates
- **Data Visualization**: 24-hour trends, 7-day history with Chart.js
- **Mobile Responsive**: Touch-friendly interface

### Advanced Weather Prediction
- **Barometric Trend Analysis**: Rate-of-change calculations
- **Multi-factor Predictions**: Temperature, humidity, pressure correlation
- **Specialized Algorithms**: Thunderstorm, fog, frost, fire weather detection
- **Confidence Scoring**: Forecast accuracy estimation

### Event Tracking
- **User Tagging**: Manual weather event logging
- **Historical Analysis**: Event correlation with sensor data
- **Model Training**: Continuous improvement of prediction algorithms

## Development

### Running in Development Mode

```bash
# Activate virtual environment
source .venv/bin/activate

# Run dashboard (masterbox)
python src/dashboard_masterbox.py

# Run sensors (weatherbox)  
python src/sensor_to_influx.py
```

### Production Deployment

```bash
# Start production dashboard
gunicorn --config config/gunicorn_config.py wsgi:application
```

### Service Management

```bash
# Check service status
sudo systemctl status weather-dashboard.service
sudo systemctl status weather-sensors.service

# View logs
sudo journalctl -u weather-dashboard.service -f
sudo journalctl -u weather-sensors.service -f

# Restart services
sudo systemctl restart weather-dashboard.service
sudo systemctl restart weather-sensors.service
```

## Configuration

### InfluxDB Setup
Edit `config/influxdb_config.py`:
```python
INFLUX_HOST = "masterbox"  # or IP address
INFLUX_PORT = 8086
INFLUX_ORG = "weatherbox"
INFLUX_BUCKET = "sensors"
INFLUX_TOKEN = "your-influx-token"
```

### Hardware Configuration
- **DHT22**: GPIO pin 4
- **MPL115A2**: I2C address 0x60, GPIO pins 17/27 for power control
- **Pressure Calibration**: -300 hPa offset applied

## Data Management

### Database Schema
- **Measurement**: `weather` (sensor readings)
- **Measurement**: `weather_events` (user-tagged events)
- **Fields**: temperature, humidity, pressure, timestamp
- **Tags**: sensor_type, location

### Maintenance Scripts
Located in `scripts/data_maintenance/`:
- `import_historical_data.py`: Bulk data import
- `fix_event_timestamps.py`: Timestamp correction utilities
- `check_events.py`: Data validation tools

## Troubleshooting

### Common Issues

1. **Service Won't Start**
   ```bash
   sudo journalctl -u weather-dashboard.service
   # Check Python path and dependencies
   ```

2. **InfluxDB Connection Errors**
   ```bash
   # Verify InfluxDB is running
   sudo systemctl status influxdb
   # Check network connectivity
   ping masterbox
   ```

3. **Sensor Reading Failures**
   ```bash
   # Check GPIO permissions
   groups weatherbox  # should include 'gpio'
   # Verify sensor wiring
   ```

### Remote Access
- SSH to weatherbox: `ssh weatherbox@weatherbox.local`
- Dashboard accessible at: `http://masterbox:5000`
- InfluxDB UI: `http://masterbox:8086`

## API Endpoints

- `GET /` - Main dashboard
- `GET /api/current` - Latest sensor reading
- `GET /api/history/<hours>` - Historical data
- `POST /api/event` - Log weather event
- `WebSocket /socket.io` - Real-time updates

## License

[Add your license information here]

## Contributing

[Add contribution guidelines here]