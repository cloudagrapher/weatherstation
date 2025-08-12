"""
DHT22 + MPL115A2 Weather Station with Web Dashboard
Temperature, humidity, and barometric pressure monitoring with weather predictions
"""

import time
import json
import threading
import math
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import Adafruit_DHT
import schedule
import os
from mpl115a2 import MPL115A2

# Configuration
DHT_SENSOR = Adafruit_DHT.DHT22
DHT_PIN = 4
DATA_FILE = "weather_data.json"
EVENTS_FILE = "weather_events.json"
MAX_READINGS = 2016  # One week at 5-minute intervals


class WeatherStation:
    def __init__(self):
        self.current_data = {}
        self.all_readings = self.load_data()
        self.pressure_sensor = MPL115A2()
        # User-tagged weather events (for model improvement)
        self.events = self.load_events()
        self.socketio = None  # Will be set after app initialization

    def set_socketio(self, socketio_instance):
        """Set the SocketIO instance for broadcasting"""
        self.socketio = socketio_instance

    def broadcast_update(self, data, message_type="new_reading"):
        """Broadcast updates to all connected clients"""
        if self.socketio:
            try:
                self.socketio.emit(
                    "message",
                    {
                        "type": message_type,
                        "data": data,
                        "timestamp": datetime.now().isoformat(),
                    },
                )
                print(f"✓ Broadcasted {message_type} to clients")
            except Exception as e:
                print(f"Broadcast error: {e}")

    def cleanup(self):
        """Clean up resources"""
        self.pressure_sensor.cleanup()

    def load_data(self):
        """Load existing weather data"""
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return []

    def save_data(self):
        """Save weather data to file"""
        try:
            # Keep only recent readings
            if len(self.all_readings) > MAX_READINGS:
                self.all_readings = self.all_readings[-MAX_READINGS:]

            with open(DATA_FILE, "w") as f:
                json.dump(self.all_readings, f, indent=2)
        except Exception as e:
            print(f"Error saving data: {e}")

    def load_events(self):
        """Load previously tagged weather events"""
        try:
            with open(EVENTS_FILE, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return []

    def save_events(self):
        """Persist tagged weather events"""
        try:
            with open(EVENTS_FILE, "w") as f:
                json.dump(self.events, f, indent=2)
        except Exception as e:
            print(f"Error saving events: {e}")

    def add_event_tag(self, event_type, intensity=None, notes=None):
        """Add a user-tagged event with a snapshot of current conditions"""
        snapshot = self.current_data.copy() if self.current_data else {}
        try:
            snapshot_predictions = self.predict_weather()
        except Exception:
            snapshot_predictions = []
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "intensity": intensity,
            "notes": notes,
            "snapshot": snapshot,
            "predictions": snapshot_predictions,
        }
        self.events.append(event)
        # Keep last 1000 events
        if len(self.events) > 1000:
            self.events = self.events[-1000:]
        self.save_events()
        # Broadcast to clients
        self.broadcast_update(event, "event_tag")
        return event

    def read_sensor(self):
        """Read DHT22 and MPL115A2 sensors and return data with improved retry logic"""
        max_attempts = 3
        delay_between_attempts = 2

        for attempt in range(max_attempts):
            try:
                # Read DHT22
                humidity, temperature_c = Adafruit_DHT.read_retry(
                    DHT_SENSOR, DHT_PIN, retries=10, delay_seconds=2
                )

                # Read MPL115A2
                pressure_hpa = self.pressure_sensor.read_pressure()

                if humidity is not None and temperature_c is not None:
                    # Validate readings are reasonable
                    if -40 <= temperature_c <= 80 and 0 <= humidity <= 100:
                        temp_f = temperature_c * 9.0 / 5.0 + 32.0

                        data = {
                            "timestamp": datetime.now().isoformat(),
                            "temperature_f": round(temp_f, 1),
                            "temperature_c": round(temperature_c, 1),
                            "humidity": round(humidity, 1),
                            "pressure_hpa": pressure_hpa,  # May be None if sensor fails
                        }

                        pressure_str = (
                            f", {pressure_hpa:.2f} hPa"
                            if pressure_hpa
                            else ", Pressure: N/A"
                        )
                        print(
                            f"Reading: {temp_f:.1f}°F ({temperature_c:.1f}°C), {humidity:.1f}%{pressure_str}"
                        )
                        return data
                    else:
                        print(
                            f"Invalid reading: {temperature_c}°C, {humidity}% (attempt {attempt + 1})"
                        )
                else:
                    print(f"No data from DHT22 (attempt {attempt + 1}/{max_attempts})")

                if attempt < max_attempts - 1:
                    time.sleep(delay_between_attempts)

            except Exception as e:
                print(f"Sensor read error (attempt {attempt + 1}): {e}")
                if attempt < max_attempts - 1:
                    time.sleep(delay_between_attempts)

        print("Failed to read sensors after all attempts")
        return None

    def collect_reading(self):
        """Enhanced collect_reading with real-time broadcasting"""
        reading = self.read_sensor()
        if reading:
            self.current_data = reading
            self.all_readings.append(reading)
            self.save_data()

            # Prepare enhanced data for broadcasting
            enhanced_data = reading.copy()
            enhanced_data["temp_trend"] = self.get_temperature_trend()
            enhanced_data["humidity_trend"] = self.get_humidity_trend()
            enhanced_data["pressure_trend"] = (
                self.get_pressure_trend()
                if reading.get("pressure_hpa")
                else "No pressure data"
            )
            enhanced_data["predictions"] = self.predict_weather()
            enhanced_data["daily_summary"] = self.get_daily_summary()

            # Broadcast to all connected clients
            self.broadcast_update(enhanced_data, "new_reading")

            print(f"✓ Data collected and broadcasted")
            return True
        else:
            # Broadcast status update about failed reading
            self.broadcast_update({"message": "Sensor reading failed"}, "status")
            print("✗ Failed to collect new reading")
            return False

    def get_temperature_trend(self, hours=2):
        """Analyze temperature trend over specified hours"""
        if len(self.all_readings) < 2:
            return "Insufficient data"

        # Get readings from the last N hours
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_readings = [
            r
            for r in self.all_readings[-100:]  # Look at last 100 readings
            if datetime.fromisoformat(r["timestamp"]) > cutoff_time
        ]

        if len(recent_readings) < 2:
            return "Insufficient data"

        temp_change = (
            recent_readings[-1]["temperature_f"] - recent_readings[0]["temperature_f"]
        )

        if temp_change > 5:
            return f"Rising rapidly (+{temp_change:.1f}°F)"
        elif temp_change > 2:
            return f"Rising (+{temp_change:.1f}°F)"
        elif temp_change < -5:
            return f"Falling rapidly ({temp_change:.1f}°F)"
        elif temp_change < -2:
            return f"Falling ({temp_change:.1f}°F)"
        else:
            return f"Stable ({temp_change:+.1f}°F)"

    def get_humidity_trend(self, hours=2):
        """Analyze humidity trend over specified hours"""
        if len(self.all_readings) < 2:
            return "Insufficient data"

        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_readings = [
            r
            for r in self.all_readings[-100:]
            if datetime.fromisoformat(r["timestamp"]) > cutoff_time
        ]

        if len(recent_readings) < 2:
            return "Insufficient data"

        humidity_change = (
            recent_readings[-1]["humidity"] - recent_readings[0]["humidity"]
        )

        if humidity_change > 15:
            return f"Rising rapidly (+{humidity_change:.1f}%)"
        elif humidity_change > 5:
            return f"Rising (+{humidity_change:.1f}%)"
        elif humidity_change < -15:
            return f"Falling rapidly ({humidity_change:.1f}%)"
        elif humidity_change < -5:
            return f"Falling ({humidity_change:.1f}%)"
        else:
            return f"Stable ({humidity_change:+.1f}%)"

    def get_recent_data(self, hours=3, minutes=None):
        """Return readings within the last N hours/minutes."""
        window = (
            timedelta(minutes=minutes)
            if minutes is not None
            else timedelta(hours=hours)
        )
        cutoff = datetime.now() - window
        return [
            r
            for r in self.all_readings
            if datetime.fromisoformat(r["timestamp"]) >= cutoff
        ]

    def predict_weather(self):
        """Enhanced weather predictions using temperature, humidity, and pressure"""
        if not self.current_data:
            return ["No current data available"]

        temp_f = self.current_data.get("temperature_f", 0)
        humidity = self.current_data.get("humidity", 0)
        pressure = self.current_data.get("pressure_hpa")

        temp_trend = self.get_temperature_trend()
        humidity_trend = self.get_humidity_trend()
        pressure_trend = self.get_pressure_trend() if pressure else "No pressure data"

        predictions = []
        confidence_scores = {}  # Track confidence for each prediction

        # Calculate dew point for fog prediction (simplified without numpy)
        def calculate_dew_point(temp_c, humidity):
            """Magnus formula approximation without numpy"""
            if humidity <= 0:
                return -100  # Return very low dew point for 0% humidity

            a = 17.27
            b = 237.7
            # Using math.log instead of np.log
            alpha = ((a * temp_c) / (b + temp_c)) + math.log(humidity / 100.0)
            dew_point_c = (b * alpha) / (a - alpha)
            return dew_point_c * 9 / 5 + 32  # Convert to F

        temp_c = (temp_f - 32) * 5 / 9
        try:
            dew_point_f = calculate_dew_point(temp_c, humidity)
        except:
            self.dew_point_f = temp_f - 20  # Fallback estimate if calculation fails

        # Calculate pressure change rate (hPa per hour)
        pressure_change_rate = 0
        if pressure and len(self.all_readings) >= 13:  # Need at least 1 hour of data
            one_hour_ago = [
                r
                for r in self.all_readings[-13:]  # ~12 readings per hour
                if r.get("pressure_hpa")
            ]
            if one_hour_ago:
                pressure_change_rate = (
                    pressure - one_hour_ago[0]["pressure_hpa"]
                ) / 1.0

        # Enhanced pressure-based predictions with confidence scores
        if pressure is not None:
            # Critical pressure thresholds with change rate consideration
            if pressure < 980:
                predictions.append("⛈️ Major storm system - severe weather imminent")
                confidence_scores["storm"] = 95
            elif pressure < 995 and pressure_change_rate < -2:
                predictions.append("⛈️ Rapidly intensifying storm approaching")
                confidence_scores["storm"] = 85
            elif pressure < 1000:
                predictions.append(
                    "🌧️ Low pressure system - rain/storms likely within 6-12 hours"
                )
                confidence_scores["rain"] = 75
            elif pressure < 1010:
                if humidity > 70:
                    predictions.append(
                        "🌦️ Unsettled weather - scattered showers possible"
                    )
                    confidence_scores["rain"] = 60
                else:
                    predictions.append("☁️ Cloudy conditions expected")
                    confidence_scores["clouds"] = 70
            elif pressure > 1030:
                predictions.append(
                    "☀️ High pressure - clear, stable weather for 24+ hours"
                )
                confidence_scores["clear"] = 90
            elif pressure > 1020:
                predictions.append("🌤️ Fair weather expected")
                confidence_scores["fair"] = 80

            # Pressure trend predictions with timing estimates
            if pressure_change_rate < -3:
                predictions.append(
                    f"⚠️ Pressure falling rapidly ({pressure_change_rate:.1f} hPa/hr) - weather deteriorating within 2-4 hours"
                )
                confidence_scores["deteriorating"] = 85
            elif pressure_change_rate < -1.5:
                predictions.append(
                    f"📉 Pressure falling ({pressure_change_rate:.1f} hPa/hr) - weather change within 6-8 hours"
                )
                confidence_scores["change"] = 70
            elif pressure_change_rate > 2:
                predictions.append(
                    f"📈 Pressure rising rapidly ({pressure_change_rate:.1f} hPa/hr) - clearing conditions"
                )
                confidence_scores["clearing"] = 80

            # Combined indicators for specific weather events
            # Thunderstorm prediction
            if (
                temp_f > 75
                and humidity > 65
                and pressure < 1015
                and pressure_change_rate < -1
            ):
                lifted_index = (temp_f - dew_point_f) - 10  # Simplified stability index
                if lifted_index < 0:
                    predictions.append(
                        "⛈️ Thunderstorm likely within 2-6 hours (unstable atmosphere)"
                    )
                    confidence_scores["thunderstorm"] = 80

            # Winter weather (if applicable)
            if temp_f < 38 and pressure < 1010 and humidity > 70:
                if temp_f <= 32:
                    predictions.append(
                        "❄️ Snow likely - winter storm conditions developing"
                    )
                    confidence_scores["snow"] = 75
                else:
                    predictions.append("🌨️ Wintry mix possible (rain/sleet/snow)")
                    confidence_scores["winter_mix"] = 65

        # Fog prediction based on dew point spread
        dew_point_spread = temp_f - dew_point_f
        if dew_point_spread < 5 and humidity > 85:
            if dew_point_spread < 2:
                predictions.append("🌫️ Dense fog likely - visibility under 1/4 mile")
                confidence_scores["fog"] = 90
            else:
                predictions.append("🌁 Fog forming - reduced visibility")
                confidence_scores["fog"] = 70

        # Heat index and comfort predictions
        if temp_f > 80:
            # Simplified heat index calculation
            heat_index = temp_f - (0.55 - 0.55 * humidity / 100) * (temp_f - 58)
            if heat_index > 105:
                predictions.append(f"🥵 Dangerous heat - heat index {heat_index:.0f}°F")
                confidence_scores["heat_danger"] = 95
            elif heat_index > 90:
                predictions.append(f"🌡️ Heat advisory - heat index {heat_index:.0f}°F")
                confidence_scores["heat_advisory"] = 85

        # Frost prediction
        if temp_f < 40 and humidity > 70 and pressure and pressure > 1020:
            if temp_f <= 32:
                predictions.append("🧊 Frost/freeze warning tonight")
                confidence_scores["frost"] = 85
            elif temp_f <= 36:
                predictions.append("❄️ Patchy frost possible in rural areas")
                confidence_scores["frost"] = 60

        # Drought/fire weather conditions
        if humidity < 25 and temp_f > 75:
            if humidity < 15:
                predictions.append("🔥 Critical fire weather - extreme caution advised")
                confidence_scores["fire"] = 90
            else:
                predictions.append("🏜️ Very dry conditions - elevated fire risk")
                confidence_scores["fire"] = 70

        # Add timing estimates based on pressure trends
        if pressure and pressure_change_rate != 0 and pressure_change_rate < -2:
            # Estimate time to significant weather based on pressure change rate
            hours_to_weather = max(2, min(6, abs(10 / pressure_change_rate)))
            predictions.append(
                f"⏰ Significant weather expected in {hours_to_weather:.0f}-{hours_to_weather+2:.0f} hours"
            )

        # Add confidence indicator to predictions
        if predictions and confidence_scores:
            avg_confidence = sum(confidence_scores.values()) / len(confidence_scores)
            if avg_confidence > 80:
                predictions.insert(0, "📊 High confidence forecast (>80%)")
            elif avg_confidence > 60:
                predictions.insert(0, "📊 Moderate confidence forecast (60-80%)")
            else:
                predictions.insert(
                    0, "📊 Low confidence forecast (<60%) - monitor closely"
                )

        # Comfort level assessment
        if (
            68 <= temp_f <= 77
            and 40 <= humidity <= 60
            and pressure
            and 1013 <= pressure <= 1023
        ):
            predictions.append("😌 Perfect comfort conditions")
        elif temp_f > 85 and humidity > 70:
            predictions.append("🥵 Oppressive conditions - limit outdoor activity")
        elif temp_f < 20:
            predictions.append("🥶 Dangerously cold - limit exposure")

        if not predictions:
            if pressure and 1013 <= pressure <= 1023:
                predictions.append(
                    "🌤️ Normal weather conditions - no significant changes expected"
                )
            else:
                predictions.append("🌤️ Stable conditions")

        # Extra rule: explicit near-term rain prediction based on pressure drop & humidity
        try:
            recent_data = self.get_recent_data(hours=3)
            if recent_data and len(recent_data) > 1:
                start_pressure = recent_data[0].get("pressure_hpa")
                end_pressure = recent_data[-1].get("pressure_hpa")
                if start_pressure is not None and end_pressure is not None:
                    pressure_drop = start_pressure - end_pressure
                    latest_humidity = recent_data[-1].get("humidity")
                    if (
                        pressure_drop >= 2
                        and latest_humidity is not None
                        and latest_humidity >= 80
                    ):
                        predictions.append(
                            "🌧️ High chance of rain within the next few hours"
                        )
        except Exception as e:
            print(f"Rain prediction check failed: {e}")
        # Fog likelihood based on sustained low T - Td spread over 15 minutes
        try:
            recent = self.get_recent_data(minutes=15)
            if recent:
                sustained = True
                for r in recent:
                    tc = r.get("temperature_c")
                    rh = r.get("humidity")
                    if tc is None or rh is None:
                        continue
                    # Magnus formula (°C)
                    a, b = 17.27, 237.7
                    alpha = ((a * tc) / (b + tc)) + math.log(max(rh, 1e-6) / 100.0)
                    td_c = (b * alpha) / (a - alpha)
                    if (tc - td_c) > 2.0:
                        sustained = False
                        break
                if sustained:
                    predictions.append("🌁 Fog likely (T−Td ≤ 2°C sustained 15 min)")
        except Exception as _e:
            print(f"Fog check failed: {_e}")

        return predictions

    def get_pressure_trend(self, hours=3):
        """Enhanced pressure trend analysis with smoothed change rate"""
        if len(self.all_readings) < 2:
            return "Insufficient data"

        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent = [
            r
            for r in self.all_readings
            if r.get("pressure_hpa") is not None
            and datetime.fromisoformat(r["timestamp"]) > cutoff_time
        ]
        if len(recent) < 6:
            return "Insufficient pressure data"

        # 30-minute window mean near start and end
        def window_mean(readings, center_time, half_window=timedelta(minutes=15)):
            lo = center_time - half_window
            hi = center_time + half_window
            vals = [
                r["pressure_hpa"]
                for r in readings
                if lo <= datetime.fromisoformat(r["timestamp"]) <= hi
            ]
            return sum(vals) / len(vals) if vals else None

        t0 = datetime.fromisoformat(recent[0]["timestamp"])
        t1 = datetime.fromisoformat(recent[-1]["timestamp"])
        c0 = t0 + timedelta(minutes=15)
        c1 = t1 - timedelta(minutes=15)
        p0 = window_mean(recent, c0) or recent[0]["pressure_hpa"]
        p1 = window_mean(recent, c1) or recent[-1]["pressure_hpa"]

        duration_hours = max((c1 - c0).total_seconds() / 3600.0, 0.1)
        pressure_change = p1 - p0
        change_rate = pressure_change / duration_hours

        if pressure_change < -3:
            return f"Falling rapidly ({pressure_change:.1f} hPa in {hours:.0f}h, {change_rate:.1f} hPa/hr)"
        elif pressure_change < -1:
            return f"Falling ({pressure_change:.1f} hPa in {hours:.0f}h, {change_rate:.1f} hPa/hr)"
        elif pressure_change > 3:
            return f"Rising rapidly (+{pressure_change:.1f} hPa in {hours:.0f}h, {change_rate:.1f} hPa/hr)"
        elif pressure_change > 1:
            return f"Rising (+{pressure_change:.1f} hPa in {hours:.0f}h, {change_rate:.1f} hPa/hr)"
        else:
            return f"Stable ({pressure_change:+.1f} hPa in {hours:.0f}h)"

    def analyze_weather_patterns(self, days=7):
        """Analyze historical patterns for better predictions"""
        if len(self.all_readings) < 100:
            return {}

        cutoff_time = datetime.now() - timedelta(days=days)
        historical_data = [
            r
            for r in self.all_readings
            if datetime.fromisoformat(r["timestamp"]) > cutoff_time
        ]

        patterns = {
            "rain_events": [],
            "pressure_before_rain": [],
            "typical_daily_range": {"temp": [], "humidity": [], "pressure": []},
            "storm_indicators": [],
        }

        # Analyze pressure drops that preceded high humidity (proxy for rain)
        for i in range(len(historical_data) - 24):  # Look 2 hours ahead
            if historical_data[i].get("pressure_hpa"):
                # Check if humidity spiked in next 2 hours
                future_humidity = [
                    historical_data[j]["humidity"]
                    for j in range(i, min(i + 24, len(historical_data)))
                ]
                if max(future_humidity) > 90 and historical_data[i]["humidity"] < 80:
                    # Likely rain event
                    patterns["pressure_before_rain"].append(
                        historical_data[i]["pressure_hpa"]
                    )
                    patterns["rain_events"].append(
                        {
                            "pressure": historical_data[i]["pressure_hpa"],
                            "humidity_before": historical_data[i]["humidity"],
                            "temp": historical_data[i]["temperature_f"],
                        }
                    )

        return patterns

    def get_daily_summary(self):
        """Get today's temperature, humidity, and pressure range"""
        today = datetime.now().date()
        today_readings = [
            r
            for r in self.all_readings
            if datetime.fromisoformat(r["timestamp"]).date() == today
        ]

        if not today_readings:
            return None

        temps = [r["temperature_f"] for r in today_readings]
        humidities = [r["humidity"] for r in today_readings]
        pressures = [
            r["pressure_hpa"]
            for r in today_readings
            if r.get("pressure_hpa") is not None
            and 800.0 <= r["pressure_hpa"] <= 1100.0
        ]

        summary = {
            "temp_high": max(temps),
            "temp_low": min(temps),
            "humidity_high": max(humidities),
            "humidity_low": min(humidities),
            "readings_count": len(today_readings),
        }

        # Add pressure data if available
        if pressures:
            summary["pressure_high"] = max(pressures)
            summary["pressure_low"] = min(pressures)
            summary["pressure_current"] = pressures[-1] if pressures else None

        return summary


# Initialize weather station
weather_station = WeatherStation()

# Flask web application
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")


# WebSocket event handlers
@socketio.on("connect")
def handle_connect():
    print("Client connected")
    # Send current data to newly connected client
    if weather_station.current_data:
        enhanced_data = weather_station.current_data.copy()
        enhanced_data["temp_trend"] = weather_station.get_temperature_trend()
        enhanced_data["humidity_trend"] = weather_station.get_humidity_trend()
        enhanced_data["pressure_trend"] = (
            weather_station.get_pressure_trend()
            if enhanced_data.get("pressure_hpa")
            else "No pressure data"
        )
        enhanced_data["predictions"] = weather_station.predict_weather()
        enhanced_data["daily_summary"] = weather_station.get_daily_summary()

        emit(
            "message",
            {
                "type": "new_reading",
                "data": enhanced_data,
                "timestamp": datetime.now().isoformat(),
            },
        )


@socketio.on("disconnect")
def handle_disconnect():
    print("Client disconnected")


@app.route("/")
def dashboard():
    """Main dashboard page"""
    return render_template("dashboard.html")


@app.route("/api/current")
def api_current():
    """Get current weather data"""
    if not weather_station.current_data:
        # Try to get a reading if we don't have current data
        weather_station.collect_reading()

        if not weather_station.current_data:
            return jsonify({"error": "No data available", "status": "sensor_error"})

    response = weather_station.current_data.copy()
    response["temp_trend"] = weather_station.get_temperature_trend()
    response["humidity_trend"] = weather_station.get_humidity_trend()
    response["pressure_trend"] = (
        weather_station.get_pressure_trend()
        if response.get("pressure_hpa")
        else "No pressure data"
    )
    response["predictions"] = weather_station.predict_weather()
    response["daily_summary"] = weather_station.get_daily_summary()
    response["status"] = "ok"

    return jsonify(response)


@app.route("/api/history")
def api_history():
    """Get historical data for charts"""
    # Return last 24 hours of data
    cutoff_time = datetime.now() - timedelta(hours=24)
    recent_data = [
        r
        for r in weather_station.all_readings
        if datetime.fromisoformat(r["timestamp"]) > cutoff_time
    ]

    return jsonify(recent_data)


@app.route("/api/history/pressure")
def api_pressure_history():
    """Get pressure trend data for last 24 hours"""
    cutoff_time = datetime.now() - timedelta(hours=24)
    pressure_data = [
        r
        for r in weather_station.all_readings
        if (
            datetime.fromisoformat(r["timestamp"]) > cutoff_time
            and r.get("pressure_hpa") is not None
        )
    ]

    return jsonify(pressure_data)


@app.route("/api/history/week")
def api_week_history():
    """Get 7-day historical data"""
    cutoff_time = datetime.now() - timedelta(days=7)
    week_data = [
        r
        for r in weather_station.all_readings
        if datetime.fromisoformat(r["timestamp"]) > cutoff_time
    ]

    # Sample data to reduce chart complexity (every 6th reading for 7 days)
    if len(week_data) > 500:
        step = len(week_data) // 500
        week_data = week_data[::step]

    return jsonify(week_data)


@app.route("/api/force_reading")
def force_reading():
    """Force a new sensor reading with real-time broadcast"""
    weather_station.broadcast_update({"message": "Taking new reading..."}, "status")
    success = weather_station.collect_reading()

    if success:
        return jsonify({"success": True, "data": weather_station.current_data})
    else:
        weather_station.broadcast_update(
            {"message": "Failed to take reading", "error": True}, "status"
        )
        return jsonify({"success": False, "error": "Sensor read failed"})


def run_scheduler():
    """Run the scheduled tasks in a separate thread"""
    while True:
        schedule.run_pending()
        time.sleep(1)


def main():
    """Main function to start the weather station with WebSocket support"""
    print("DHT22 + MPL115A2 Weather Station Starting...")

    try:
        # Set up the SocketIO instance
        weather_station.set_socketio(socketio)

        # Take initial reading
        weather_station.collect_reading()

        # Schedule readings every 5 minutes
        schedule.every(5).minutes.do(weather_station.collect_reading)

        # Start scheduler in background thread
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()

        # Create templates directory if it doesn't exist
        os.makedirs("templates", exist_ok=True)

        print("Weather station running with real-time updates!")
        print("Access dashboard at: http://localhost:5000")
        print("WebSocket endpoint: ws://localhost:5000/ws")

        # Start web server with SocketIO support
        socketio.run(app, host="0.0.0.0", port=5000, debug=False)

    except KeyboardInterrupt:
        print("\nShutting down weather station...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        weather_station.cleanup()
        print("Cleanup complete")


if __name__ == "__main__":
    main()


@app.route("/api/tag_event", methods=["POST"])
def api_tag_event():
    """Accept a user-tagged weather event"""
    try:
        payload = request.get_json(force=True) or {}
        event_type = payload.get("event_type")
        intensity = payload.get("intensity")
        notes = payload.get("notes")
        if not event_type:
            return jsonify({"success": False, "error": "event_type required"}), 400
        evt = weather_station.add_event_tag(event_type, intensity, notes)
        return jsonify({"success": True, "event": evt})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/events")
def api_events():
    """Return recent tagged events (optional ?limit=N)"""
    try:
        limit = int(request.args.get("limit", "20"))
    except ValueError:
        limit = 20
    return jsonify(weather_station.events[-limit:][::-1])
