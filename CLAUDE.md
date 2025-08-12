# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Setup

**Python Environment:**

- Uses Python 3.13 with a virtual environment at `.venv/`
- Activate with: `source .venv/bin/activate`
- Dependencies listed in `requirements.txt`
- Install dependencies: `python -m pip install -r requirements.txt`

**Running the Application:**

- Main script: `python dht22_weather_station.py`
- Web dashboard accessible at: [http://localhost:5000](http://localhost:5000)
- Uses Flask with SocketIO for real-time WebSocket communication

**Production Deployment:**

- Systemd service configuration available in `services/README.md`
- Service runs as `weatherbox` user on Raspberry Pi
- Auto-restart enabled with 10-second delay on failure

## Architecture Overview

**Core Components:**

- `WeatherStation` class: Main application logic, data collection, and prediction algorithms
- `MPL115A2` class: Hardware interface for barometric pressure sensor via I2C/GPIO
- Flask web server with SocketIO for real-time dashboard updates
- Data persistence using JSON files (`weather_data.json`, `weather_events.json`)

**Hardware Integration:**

- DHT22 sensor (GPIO pin 4): Temperature and humidity readings
- MPL115A2 sensor (I2C address 0x60): Barometric pressure with GPIO control pins
- Raspberry Pi GPIO interface for sensor control and data collection

**Data Flow:**

- Scheduled readings every 5 minutes using the `schedule` library
- Real-time broadcasting to web clients via WebSocket
- Historical data stored with rolling window (MAX_READINGS = 2016)
- Weather predictions based on pressure trends, temperature, and humidity patterns

**Web Interface:**

- Single-page dashboard (`templates/dashboard.html`) with real-time updates
- Chart.js for data visualization (24-hour, pressure trends, 7-day history)
- User event tagging system for model improvement
- Mobile-responsive design with touch-friendly controls

**Key Features:**

- Advanced weather prediction algorithms using barometric pressure trends
- Real-time WebSocket updates for live data streaming
- User-contributed weather event tagging for prediction model enhancement
- Comprehensive data visualization with multiple chart types
- Mobile-optimized responsive interface

## Development Notes

**Testing the Application:**

- No formal test framework configured - manual testing via web interface
- Use "Take Reading Now" button for immediate sensor testing
- Monitor WebSocket connection status in browser console

**Data Files:**

- `weather_data.json`: Rolling historical sensor readings
- `weather_events.json`: User-tagged weather events for model training

**Directory Structure:**

- `services/`: Contains systemd service configuration for production deployment
- `templates/`: Flask HTML templates for the web interface

**GPIO Requirements:**

- Designed for Raspberry Pi with GPIO access
- DHT22 on GPIO 4, MPL115A2 with reset/shutdown control on GPIO 17/27
- Uses RPi.GPIO and smbus2 libraries for hardware communication
