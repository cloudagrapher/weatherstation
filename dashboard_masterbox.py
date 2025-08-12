#!/home/masterbox/weatherstation/.venv/bin/python
"""
Weather Dashboard for Masterbox
Flask web dashboard that pulls data from InfluxDB instead of sensors
Maintains the same functionality and interface as the original
"""

import json
import math
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
from influxdb_data_service import WeatherDataService


class WeatherDashboard:
    """Weather dashboard that reads data from InfluxDB"""
    
    def __init__(self):
        self.data_service = WeatherDataService()
        self.current_data = {}
        self.socketio = None
        self._update_current_data()
    
    def get_recent_events(self, limit: int = 20):
        """Get recent tagged weather events from InfluxDB"""
        return self.data_service.get_recent_weather_events(limit=limit)
    
    def _update_current_data(self):
        """Update current data from InfluxDB"""
        self.current_data = self.data_service.get_current_data() or {}
    
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
    
    def get_current_reading(self):
        """Get current reading with trends and predictions"""
        self._update_current_data()
        
        if not self.current_data:
            return None
        
        enhanced_data = self.current_data.copy()
        enhanced_data["temp_trend"] = self.get_temperature_trend()
        enhanced_data["humidity_trend"] = self.get_humidity_trend()
        enhanced_data["pressure_trend"] = self.get_pressure_trend()
        predictions = self.predict_weather()
        enhanced_data["predictions"] = predictions
        enhanced_data["daily_summary"] = self.get_daily_summary()
        
        # Store predictions in InfluxDB for historical analysis
        if predictions:
            self.data_service.store_weather_predictions(predictions, self.current_data)
        
        return enhanced_data
    
    def get_temperature_trend(self, hours=2):
        """Analyze temperature trend over specified hours"""
        recent_readings = self.data_service.get_recent_data(hours=hours)
        
        if len(recent_readings) < 2:
            return "Insufficient data"
        
        temp_change = recent_readings[-1]["temperature_f"] - recent_readings[0]["temperature_f"]
        
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
        recent_readings = self.data_service.get_recent_data(hours=hours)
        
        if len(recent_readings) < 2:
            return "Insufficient data"
        
        humidity_change = recent_readings[-1]["humidity"] - recent_readings[0]["humidity"]
        
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
    
    def get_pressure_trend(self, hours=3):
        """Enhanced pressure trend analysis"""
        recent_readings = self.data_service.get_recent_data(hours=hours)
        recent_with_pressure = [r for r in recent_readings if "pressure_hpa" in r]
        
        if len(recent_with_pressure) < 6:
            return "Insufficient pressure data"
        
        # Calculate pressure change over the time period
        pressure_change = recent_with_pressure[-1]["pressure_hpa"] - recent_with_pressure[0]["pressure_hpa"]
        
        # Calculate time difference
        start_time = datetime.fromisoformat(recent_with_pressure[0]["timestamp"])
        end_time = datetime.fromisoformat(recent_with_pressure[-1]["timestamp"])
        duration_hours = max((end_time - start_time).total_seconds() / 3600.0, 0.1)
        
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
    
    def predict_weather(self):
        """Enhanced weather predictions using temperature, humidity, and pressure"""
        if not self.current_data:
            return ["No current data available"]
        
        temp_f = self.current_data.get("temperature_f", 0)
        humidity = self.current_data.get("humidity", 0)
        pressure = self.current_data.get("pressure_hpa")
        
        predictions = []
        confidence_scores = {}
        
        # Calculate dew point for fog prediction
        def calculate_dew_point(temp_c, humidity):
            if humidity <= 0:
                return -100
            
            a = 17.27
            b = 237.7
            alpha = ((a * temp_c) / (b + temp_c)) + math.log(humidity / 100.0)
            dew_point_c = (b * alpha) / (a - alpha)
            return dew_point_c * 9 / 5 + 32
        
        temp_c = (temp_f - 32) * 5 / 9
        try:
            dew_point_f = calculate_dew_point(temp_c, humidity)
        except:
            dew_point_f = temp_f - 20
        
        # Calculate pressure change rate
        pressure_change_rate = 0
        if pressure:
            recent_readings = self.data_service.get_recent_data(hours=1)
            pressure_readings = [r for r in recent_readings if "pressure_hpa" in r]
            
            if len(pressure_readings) >= 2:
                pressure_change_rate = (
                    pressure_readings[-1]["pressure_hpa"] - pressure_readings[0]["pressure_hpa"]
                ) / 1.0
        
        # Enhanced pressure-based predictions
        if pressure is not None:
            if pressure < 980:
                predictions.append("⛈️ Major storm system - severe weather imminent")
                confidence_scores["storm"] = 95
            elif pressure < 995 and pressure_change_rate < -2:
                predictions.append("⛈️ Rapidly intensifying storm approaching")
                confidence_scores["storm"] = 85
            elif pressure < 1000:
                predictions.append("🌧️ Low pressure system - rain/storms likely within 6-12 hours")
                confidence_scores["rain"] = 75
            elif pressure < 1010:
                if humidity > 70:
                    predictions.append("🌦️ Unsettled weather - scattered showers possible")
                    confidence_scores["rain"] = 60
                else:
                    predictions.append("☁️ Cloudy conditions expected")
                    confidence_scores["clouds"] = 70
            elif pressure > 1030:
                predictions.append("☀️ High pressure - clear, stable weather for 24+ hours")
                confidence_scores["clear"] = 90
            elif pressure > 1020:
                predictions.append("🌤️ Fair weather expected")
                confidence_scores["fair"] = 80
            
            # Pressure trend predictions
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
            
            # Thunderstorm prediction
            if (temp_f > 75 and humidity > 65 and pressure < 1015 and pressure_change_rate < -1):
                lifted_index = (temp_f - dew_point_f) - 10
                if lifted_index < 0:
                    predictions.append("⛈️ Thunderstorm likely within 2-6 hours (unstable atmosphere)")
                    confidence_scores["thunderstorm"] = 80
            
            # Winter weather
            if temp_f < 38 and pressure < 1010 and humidity > 70:
                if temp_f <= 32:
                    predictions.append("❄️ Snow likely - winter storm conditions developing")
                    confidence_scores["snow"] = 75
                else:
                    predictions.append("🌨️ Wintry mix possible (rain/sleet/snow)")
                    confidence_scores["winter_mix"] = 65
        
        # Fog prediction
        dew_point_spread = temp_f - dew_point_f
        if dew_point_spread < 5 and humidity > 85:
            if dew_point_spread < 2:
                predictions.append("🌫️ Dense fog likely - visibility under 1/4 mile")
                confidence_scores["fog"] = 90
            else:
                predictions.append("🌁 Fog forming - reduced visibility")
                confidence_scores["fog"] = 70
        
        # Heat index
        if temp_f > 80:
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
        
        # Fire weather conditions
        if humidity < 25 and temp_f > 75:
            if humidity < 15:
                predictions.append("🔥 Critical fire weather - extreme caution advised")
                confidence_scores["fire"] = 90
            else:
                predictions.append("🏜️ Very dry conditions - elevated fire risk")
                confidence_scores["fire"] = 70
        
        # Add confidence indicator
        if predictions and confidence_scores:
            avg_confidence = sum(confidence_scores.values()) / len(confidence_scores)
            if avg_confidence > 80:
                predictions.insert(0, "📊 High confidence forecast (>80%)")
            elif avg_confidence > 60:
                predictions.insert(0, "📊 Moderate confidence forecast (60-80%)")
            else:
                predictions.insert(0, "📊 Low confidence forecast (<60%) - monitor closely")
        
        # Comfort level assessment
        if (68 <= temp_f <= 77 and 40 <= humidity <= 60 and pressure and 1013 <= pressure <= 1023):
            predictions.append("😌 Perfect comfort conditions")
        elif temp_f > 85 and humidity > 70:
            predictions.append("🥵 Oppressive conditions - limit outdoor activity")
        elif temp_f < 20:
            predictions.append("🥶 Dangerously cold - limit exposure")
        
        if not predictions:
            if pressure and 1013 <= pressure <= 1023:
                predictions.append("🌤️ Normal weather conditions - no significant changes expected")
            else:
                predictions.append("🌤️ Stable conditions")
        
        return predictions
    
    def get_daily_summary(self):
        """Get today's temperature, humidity, and pressure range"""
        return self.data_service.get_daily_summary()
    
    def add_event_tag(self, event_type, intensity=None, notes=None):
        """Add a user-tagged event with current conditions stored in InfluxDB"""
        self._update_current_data()
        current_conditions = self.current_data.copy()
        
        # Store the event in InfluxDB
        success = self.data_service.store_weather_event(
            event_type=event_type,
            intensity=intensity,
            notes=notes,
            current_conditions=current_conditions
        )
        
        if success:
            # Create event object for immediate broadcast
            event = {
                "timestamp": datetime.now().isoformat(),
                "event_type": event_type,
                "intensity": intensity,
                "notes": notes,
                "conditions": current_conditions,
                "predictions": self.predict_weather() if current_conditions else []
            }
            
            # Broadcast to all connected clients
            self.broadcast_update(event, "event_tag")
            
            # Also broadcast updated events list
            recent_events = self.get_recent_events(20)
            self.broadcast_update({"events": recent_events}, "events_update")
            
            return event
        else:
            raise Exception("Failed to store event in InfluxDB")


# Initialize dashboard
dashboard = WeatherDashboard()

# Flask web application
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")


# WebSocket event handlers
@socketio.on("connect")
def handle_connect():
    print("Client connected")
    # Send current data to newly connected client
    current_reading = dashboard.get_current_reading()
    if current_reading:
        emit(
            "message",
            {
                "type": "new_reading",
                "data": current_reading,
                "timestamp": datetime.now().isoformat(),
            },
        )


@socketio.on("disconnect")
def handle_disconnect():
    print("Client disconnected")


# API Routes
@app.route("/")
def dashboard_page():
    """Main dashboard page"""
    return render_template("dashboard.html")


@app.route("/api/current")
def api_current():
    """Get current weather data"""
    current_reading = dashboard.get_current_reading()
    
    if not current_reading:
        return jsonify({"error": "No data available", "status": "sensor_error"})
    
    current_reading["status"] = "ok"
    return jsonify(current_reading)


@app.route("/api/history")
def api_history():
    """Get historical data for charts"""
    recent_data = dashboard.data_service.get_historical_data(hours=24)
    return jsonify(recent_data)


@app.route("/api/history/pressure")
def api_pressure_history():
    """Get pressure trend data for last 24 hours"""
    pressure_data = dashboard.data_service.get_pressure_history(hours=24)
    return jsonify(pressure_data)


@app.route("/api/history/week")
def api_week_history():
    """Get 7-day historical data"""
    week_data = dashboard.data_service.get_week_history()
    return jsonify(week_data)


@app.route("/api/force_reading")
def force_reading():
    """Force a refresh of current data"""
    dashboard.broadcast_update({"message": "Refreshing data..."}, "status")
    
    try:
        dashboard._update_current_data()
        current_reading = dashboard.get_current_reading()
        
        if current_reading:
            dashboard.broadcast_update(current_reading, "new_reading")
            return jsonify({"success": True, "data": current_reading})
        else:
            dashboard.broadcast_update(
                {"message": "No data available from sensors", "error": True}, "status"
            )
            return jsonify({"success": False, "error": "No sensor data available"})
    except Exception as e:
        dashboard.broadcast_update(
            {"message": f"Error refreshing data: {e}", "error": True}, "status"
        )
        return jsonify({"success": False, "error": str(e)})


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
        
        evt = dashboard.add_event_tag(event_type, intensity, notes)
        return jsonify({"success": True, "event": evt})
    
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/events")
def api_events():
    """Return recent tagged events from InfluxDB"""
    try:
        limit = int(request.args.get("limit", "20"))
    except ValueError:
        limit = 20
    
    events = dashboard.get_recent_events(limit)
    return jsonify(events)


@app.route("/api/analysis")
def api_analysis():
    """Get weather analysis for a date range"""
    from datetime import datetime
    import pytz
    
    try:
        # Get parameters
        start_str = request.args.get("start")
        end_str = request.args.get("end")
        
        if not start_str:
            return jsonify({"error": "start date required (YYYY-MM-DD format)"}), 400
        
        eastern_tz = pytz.timezone('America/New_York')
        
        # Parse start date
        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d")
            start_date = eastern_tz.localize(start_date)
        except ValueError:
            return jsonify({"error": "Invalid start date format. Use YYYY-MM-DD"}), 400
        
        # Parse end date (optional)
        end_date = None
        if end_str:
            try:
                end_date = datetime.strptime(end_str, "%Y-%m-%d")
                end_date = eastern_tz.localize(end_date)
                # Add one day to include the full end date
                end_date = end_date + timedelta(days=1)
            except ValueError:
                return jsonify({"error": "Invalid end date format. Use YYYY-MM-DD"}), 400
        
        # Get analysis data
        analysis = dashboard.data_service.get_weather_analysis(start_date, end_date)
        return jsonify(analysis)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/predictions")
def api_predictions():
    """Get historical predictions for a date range"""
    from datetime import datetime
    import pytz
    
    try:
        # Get parameters
        start_str = request.args.get("start")
        end_str = request.args.get("end")
        
        if not start_str:
            return jsonify({"error": "start date required (YYYY-MM-DD format)"}), 400
        
        eastern_tz = pytz.timezone('America/New_York')
        
        # Parse start date
        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d")
            start_date = eastern_tz.localize(start_date)
        except ValueError:
            return jsonify({"error": "Invalid start date format. Use YYYY-MM-DD"}), 400
        
        # Parse end date (optional)
        end_date = None
        if end_str:
            try:
                end_date = datetime.strptime(end_str, "%Y-%m-%d")
                end_date = eastern_tz.localize(end_date)
                # Add one day to include the full end date
                end_date = end_date + timedelta(days=1)
            except ValueError:
                return jsonify({"error": "Invalid end date format. Use YYYY-MM-DD"}), 400
        
        # Get predictions
        predictions = dashboard.data_service.get_historical_predictions(start_date, end_date)
        return jsonify(predictions)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/analysis")
def analysis_page():
    """Historical analysis page"""
    return render_template("analysis.html")


def update_data_periodically():
    """Periodically update current data and broadcast to clients"""
    while True:
        try:
            dashboard._update_current_data()
            current_reading = dashboard.get_current_reading()
            
            if current_reading:
                dashboard.broadcast_update(current_reading, "new_reading")
                print("✓ Data updated and broadcasted")
            else:
                print("✗ No current data available")
        
        except Exception as e:
            print(f"Error in periodic update: {e}")
        
        # Wait 30 seconds before next update
        time.sleep(30)


def main():
    """Main function to start the weather dashboard"""
    print("Weather Dashboard Starting on Masterbox...")
    print("Reading data from InfluxDB instead of sensors")
    
    try:
        # Set up the SocketIO instance
        dashboard.set_socketio(socketio)
        
        # Start periodic data update thread
        update_thread = threading.Thread(target=update_data_periodically, daemon=True)
        update_thread.start()
        
        print("Dashboard running with InfluxDB data!")
        print("Access dashboard at: http://localhost:5000")
        
        # Start web server with SocketIO support (for development)
        socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)
    
    except KeyboardInterrupt:
        print("\nShutting down dashboard...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        dashboard.data_service.close()
        print("Cleanup complete")


if __name__ == "__main__":
    main()