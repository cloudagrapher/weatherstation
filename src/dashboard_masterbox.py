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
from .influxdb_data_service import WeatherDataService
from .weather_api_service import WeatherAPIService

# Seasonal fog probability for Smyrna, GA (30080) humid subtropical climate
FOG_SEASONAL_PROBABILITY = {
    'winter': {  # Dec-Feb
        'overnight': 0.25,  # 12am-6am
        'morning': 0.30,    # 6am-10am
        'midday': 0.02,     # 10am-3pm
        'evening': 0.08     # 3pm-12am
    },
    'spring': {  # Mar-May
        'overnight': 0.20,
        'morning': 0.25,
        'midday': 0.01,
        'evening': 0.05
    },
    'summer': {  # Jun-Aug
        'overnight': 0.15,
        'morning': 0.20,
        'midday': 0.001,    # Almost never
        'evening': 0.03
    },
    'fall': {  # Sep-Nov
        'overnight': 0.22,
        'morning': 0.28,
        'midday': 0.02,
        'evening': 0.07
    }
}


class WeatherDashboard:
    """Weather dashboard that reads data from InfluxDB"""
    
    def __init__(self):
        self.data_service = WeatherDataService()
        self.api_service = WeatherAPIService()
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
        
        # Calculate feels like temperature and comfort descriptions
        if "temperature_f" in self.current_data and "humidity" in self.current_data:
            feels_like = self.calculate_feels_like(
                self.current_data["temperature_f"], 
                self.current_data["humidity"]
            )
            enhanced_data["feels_like_f"] = feels_like
            enhanced_data["comfort_descriptions"] = self.get_comfort_description(
                feels_like, 
                self.current_data["humidity"]
            )
        
        predictions = self.predict_weather()
        enhanced_data["predictions"] = predictions
        enhanced_data["daily_summary"] = self.get_daily_summary()
        
        # Add official weather comparison
        enhanced_data["api_comparison"] = self.get_api_comparison()
        
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
    
    def get_pressure_trend(self, hours=1):
        """Enhanced pressure trend analysis"""
        recent_readings = self.data_service.get_recent_data(hours=hours)
        recent_with_pressure = [r for r in recent_readings if "pressure_hpa" in r]
        
        if len(recent_with_pressure) < 2:  # Reduced from 6 to 2
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
    
    def calculate_feels_like(self, temp_f, humidity, wind_mph=0):
        """Calculate 'feels like' temperature based on conditions"""
        temp_c = (temp_f - 32) * 5/9
        
        # Hot weather: Use Heat Index
        if temp_f >= 80 and humidity >= 40:
            return self.heat_index(temp_f, humidity)
        
        # Cold weather with wind: Use Wind Chill
        elif temp_f <= 50 and wind_mph >= 3:
            return self.wind_chill(temp_f, wind_mph)
        
        # Moderate conditions: Use simplified apparent temperature
        else:
            return self.apparent_temperature(temp_c, humidity, wind_mph * 0.44704)  # mph to m/s

    def heat_index(self, temp_f, humidity):
        """Calculate heat index for hot, humid conditions"""
        if temp_f < 80 or humidity < 40:
            return temp_f
        
        # Full Rothfusz regression equation
        hi = -42.379 + 2.04901523*temp_f + 10.14333127*humidity
        hi += -0.22475541*temp_f*humidity - 6.83783e-3*temp_f**2
        hi += -5.481717e-2*humidity**2 + 1.22874e-3*temp_f**2*humidity
        hi += 8.5282e-4*temp_f*humidity**2 - 1.99e-6*temp_f**2*humidity**2
        
        # Adjustments for extreme conditions
        if humidity < 13 and 80 <= temp_f <= 112:
            hi -= ((13-humidity)/4) * math.sqrt((17-abs(temp_f-95.))/17)
        elif humidity > 85 and 80 <= temp_f <= 87:
            hi += ((humidity-85)/10) * ((87-temp_f)/5)
        
        return round(hi, 1)

    def wind_chill(self, temp_f, wind_mph):
        """Calculate wind chill for cold, windy conditions"""
        if temp_f > 50 or wind_mph < 3:
            return temp_f
        
        wc = 35.74 + 0.6215*temp_f - 35.75*(wind_mph**0.16)
        wc += 0.4275*temp_f*(wind_mph**0.16)
        
        return round(wc, 1)

    def apparent_temperature(self, temp_c, humidity, wind_ms):
        """Calculate apparent temperature for moderate conditions"""
        # Vapor pressure in hPa
        e = (humidity/100) * 6.105 * math.exp(17.27*temp_c/(237.7+temp_c))
        
        # Apparent temperature
        at = temp_c + 0.33*e - 0.7*wind_ms - 4.0
        
        # Convert back to Fahrenheit
        return round(at * 9/5 + 32, 1)

    def get_comfort_description(self, feels_like, humidity):
        """Provide human-readable comfort description"""
        descriptions = []
        
        if feels_like < 32:
            descriptions.append("❄️ Freezing conditions")
        elif feels_like < 50:
            descriptions.append("🧥 Cold - dress warmly")
        elif feels_like < 65:
            descriptions.append("🧤 Cool - light jacket recommended")
        elif 65 <= feels_like <= 75:
            descriptions.append("😌 Comfortable conditions")
        elif feels_like <= 80:
            descriptions.append("☀️ Warm and pleasant")
        elif feels_like <= 90:
            descriptions.append("🌡️ Hot - seek shade")
        elif feels_like <= 105:
            descriptions.append("🥵 Very hot - limit outdoor activity")
        else:
            descriptions.append("🚨 Dangerous heat - stay indoors")
        
        # Humidity comfort
        if humidity > 70:
            descriptions.append("💧 High humidity - feels muggy")
        elif humidity < 30:
            descriptions.append("🏜️ Low humidity - may feel dry")
        
        return descriptions
    
    def detect_current_conditions(self):
        """Detect current weather conditions based on sensor readings - optimized for Smyrna, GA"""
        if not self.current_data:
            return []
        
        temp_f = self.current_data.get("temperature_f", 0)
        humidity = self.current_data.get("humidity", 0)
        pressure = self.current_data.get("pressure_hpa")
        
        current_conditions = []
        
        # Calculate dew point for thunderstorm analysis
        temp_c = (temp_f - 32) * 5/9
        try:
            a, b = 17.27, 237.7
            alpha = ((a * temp_c) / (b + temp_c)) + math.log(humidity / 100.0)
            dew_point_c = (b * alpha) / (a - alpha)
            dew_point_f = (dew_point_c * 9/5) + 32
            temp_dew_spread = temp_f - dew_point_f
        except:
            dew_point_f = temp_f - 20  # fallback
            temp_dew_spread = 20
        
        # Get pressure change rate for storm analysis
        pressure_change_rate = 0
        if pressure:
            recent_readings = self.data_service.get_recent_data(hours=1)
            pressure_readings = [r for r in recent_readings if "pressure_hpa" in r]
            if len(pressure_readings) >= 2:
                pressure_change_rate = (pressure_readings[-1]["pressure_hpa"] - pressure_readings[0]["pressure_hpa"]) / 1.0
        
        # Check for sustained high humidity (10+ minutes)
        humidity_sustained = False
        if humidity >= 92:
            recent_10min = self.data_service.get_recent_data(minutes=10)
            if len(recent_10min) >= 3:  # At least 3 readings in 10 minutes
                high_humidity_count = sum(1 for r in recent_10min if r.get("humidity", 0) >= 92)
                humidity_sustained = high_humidity_count >= len(recent_10min) * 0.7  # 70% of readings
        
        # IMPROVED HEAVY PRECIPITATION DETECTION
        if humidity >= 92 and (pressure_change_rate <= -1.5 or humidity_sustained):
            current_conditions.append("🌧️ HEAVY PRECIPITATION LIKELY/ONGOING - High humidity with pressure fall or sustained moisture")
        elif humidity > 85:
            current_conditions.append("🌦️ LIGHT PRECIPITATION POSSIBLE - Very high humidity")
        
        # IMPROVED THUNDERSTORM CONDITIONS FOR SMYRNA, GA
        # Primary rule: T ≥ 82°F, dewpoint ≥ 66°F, pressure falling ≥ 1.5 hPa/hr
        if temp_f >= 82 and dew_point_f >= 66 and pressure_change_rate <= -1.5:
            current_conditions.append("⛈️ THUNDERSTORM LIKELY (2-6h) - Heat + moisture + pressure fall")
        # Alternative rule: T ≥ 78°F, dewpoint ≥ 70°F, spread ≤ 12°F
        elif temp_f >= 78 and dew_point_f >= 70 and temp_dew_spread <= 12:
            current_conditions.append("⚡ THUNDERSTORM POSSIBLE - High dewpoint with low spread")
        # Bonus signals: brief RH spike or pressure volatility
        elif temp_f >= 75:
            # Check for humidity spike in last 30 minutes
            humidity_spike = False
            recent_30min = self.data_service.get_recent_data(minutes=30)
            if len(recent_30min) >= 2:
                humidity_change = recent_30min[-1].get("humidity", 0) - recent_30min[0].get("humidity", 0)
                if humidity_change >= 8:  # +8-12% spike
                    humidity_spike = True
            
            if humidity_spike:
                current_conditions.append("⚡ THUNDERSTORM POSSIBLE - Rapid moisture increase detected")
        
        # PRESSURE VOLATILITY (indicates active weather)
        recent_readings = self.data_service.get_recent_data(minutes=30)
        if len(recent_readings) >= 3:
            pressure_values = [r["pressure_hpa"] for r in recent_readings if r.get("pressure_hpa") is not None]
            if len(pressure_values) >= 3:
                pressure_range = max(pressure_values) - min(pressure_values)
                if pressure_range > 2:
                    current_conditions.append("🌪️ PRESSURE VOLATILITY - Active weather system present")
        
        return current_conditions

    def predict_fog(self):
        """Enhanced fog prediction for Smyrna, GA climate"""
        if not self.current_data:
            return None
        
        # Current conditions
        temp_f = self.current_data.get('temperature_f', 0)
        humidity = self.current_data.get('humidity', 0)
        pressure = self.current_data.get('pressure_hpa')
        
        # Convert to Celsius for dew point calculation
        temp_c = (temp_f - 32) * 5/9
        
        # Calculate dew point using Magnus formula
        a = 17.27
        b = 237.7
        alpha = ((a * temp_c) / (b + temp_c)) + math.log(humidity / 100.0)
        dewpoint_c = (b * alpha) / (a - alpha)
        dewpoint_f = (dewpoint_c * 9/5) + 32
        
        # Temperature-dewpoint spread
        temp_dewpoint_spread = temp_f - dewpoint_f
        
        # Get time-based factors
        current_hour = datetime.now().hour
        current_month = datetime.now().month
        
        # Determine season
        if current_month in [12, 1, 2]:
            season = 'winter'
        elif current_month in [3, 4, 5]:
            season = 'spring'
        elif current_month in [6, 7, 8]:
            season = 'summer'
        else:
            season = 'fall'
        
        # Determine time period
        if 0 <= current_hour < 6:
            time_period = 'overnight'
        elif 6 <= current_hour < 10:
            time_period = 'morning'
        elif 10 <= current_hour < 15:
            time_period = 'midday'
        else:
            time_period = 'evening'
        
        # Base seasonal probability
        base_probability = FOG_SEASONAL_PROBABILITY[season][time_period]
        
        # Fog likelihood factors
        fog_score = 0
        fog_conditions = []
        
        # Temperature-dewpoint spread (most critical factor)
        if temp_dewpoint_spread <= 2:
            fog_score += 40
            fog_conditions.append(f"Dew point very close ({temp_dewpoint_spread:.1f}°F spread)")
        elif temp_dewpoint_spread <= 4:
            fog_score += 20
            fog_conditions.append(f"Dew point close ({temp_dewpoint_spread:.1f}°F spread)")
        elif temp_dewpoint_spread <= 6:
            fog_score += 5
        
        # Humidity thresholds (adjusted for humid climate)
        if humidity >= 95:
            fog_score += 30
            fog_conditions.append("Very high humidity")
        elif humidity >= 90:
            fog_score += 15
        elif humidity >= 85:
            fog_score += 5
        
        # Pressure conditions
        if pressure and 1015 <= pressure <= 1025:
            fog_score += 10  # High pressure systems favor radiation fog
            fog_conditions.append("Stable high pressure")
        
        # Temperature conditions for Smyrna
        if season == 'summer':
            # Summer fog is rare during day, mostly early morning
            if time_period == 'morning' and 65 <= temp_f <= 75:
                fog_score += 15
                fog_conditions.append("Ideal morning fog temperature")
            elif time_period == 'midday' or time_period == 'evening':
                fog_score -= 30  # Strong negative for summer midday/evening
        else:
            # Fall/Winter/Spring fog temperature ranges
            if 35 <= temp_f <= 55:
                fog_score += 10
                fog_conditions.append("Favorable fog temperature range")
        
        # Wind conditions (need to add wind sensor for this)
        # For now, assume calm conditions if pressure is stable
        if pressure:
            pressure_trend = self.get_pressure_trend(hours=1)
            if "Stable" in pressure_trend:
                fog_score += 5
                fog_conditions.append("Likely calm conditions")
        
        # Recent rain check (increases fog probability)
        # Check if humidity increased significantly in last 6 hours
        humidity_trend = self.get_humidity_trend(hours=6)
        if "Rising" in humidity_trend and "rapidly" in humidity_trend.lower():
            fog_score += 10
            fog_conditions.append("Recent moisture increase")
        
        # Apply seasonal and time modifiers
        fog_score *= base_probability
        
        # Summer daytime penalty (aggressive reduction)
        if season == 'summer' and time_period in ['midday', 'evening']:
            fog_score *= 0.1  # 90% reduction
        
        # Calculate final probability
        fog_probability = min(fog_score, 95)  # Cap at 95%
        
        # Generate prediction message
        if fog_probability >= 70:
            severity = "Very likely"
            icon = "🌫️"
        elif fog_probability >= 40:
            severity = "Likely"
            icon = "🌁"
        elif fog_probability >= 20:
            severity = "Possible"
            icon = "🌫️"
        else:
            return None  # Don't report low probability fog
        
        # Build detailed message
        message = f"{icon} Fog {severity} ({fog_probability:.0f}% chance)"
        
        if fog_conditions:
            message += f" - {', '.join(fog_conditions[:2])}"  # Limit to 2 conditions
        
        # Add time-specific guidance
        if time_period == 'evening' and fog_probability >= 40:
            message += " - Developing overnight"
        elif time_period == 'overnight' and fog_probability >= 40:
            message += " - Through early morning"
        elif time_period == 'morning' and fog_probability >= 40:
            message += " - Clearing by mid-morning"
        
        return {
            'prediction': message,
            'probability': fog_probability,
            'dewpoint_f': dewpoint_f,
            'temp_spread': temp_dewpoint_spread,
            'conditions': fog_conditions
        }

    def predict_weather(self):
        """Enhanced weather predictions with current condition detection"""
        if not self.current_data:
            return ["No current data available"]
        
        predictions = []
        
        # FIRST: Check what's happening RIGHT NOW
        current_conditions = self.detect_current_conditions()
        if current_conditions:
            predictions.extend(current_conditions)
            predictions.append("---")  # Separator
        
        # THEN: Add traditional forecasting
        temp_f = self.current_data.get("temperature_f", 0)
        humidity = self.current_data.get("humidity", 0)
        pressure = self.current_data.get("pressure_hpa")
        
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
            
            # Pressure trend predictions with storm clearing detection
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
                # Enhanced storm clearing detection
                if humidity > 80:
                    predictions.append(
                        f"🌤️ STORM CLEARING - Pressure rising rapidly ({pressure_change_rate:.1f} hPa/hr) after high humidity"
                    )
                    confidence_scores["storm_clearing"] = 90
                else:
                    predictions.append(
                        f"📈 Pressure rising rapidly ({pressure_change_rate:.1f} hPa/hr) - clearing conditions"
                    )
                    confidence_scores["clearing"] = 80
            elif pressure_change_rate > 1:
                if humidity > 75:
                    predictions.append(
                        f"🌤️ Weather improving - Pressure rising ({pressure_change_rate:.1f} hPa/hr) as moisture decreases"
                    )
                    confidence_scores["improving"] = 75
            
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
        
        # Enhanced fog prediction using climatological data
        fog_prediction = self.predict_fog()
        if fog_prediction:
            predictions.append(fog_prediction['prediction'])
            confidence_scores["fog"] = fog_prediction['probability']
        
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
        
        # IMPROVED CONFIDENCE CALCULATION using noisy-OR approach
        if predictions and confidence_scores:
            # Separate severe signals from routine ones
            severe_signals = []
            routine_signals = []
            
            for signal_type, confidence in confidence_scores.items():
                # Severe signals get priority weighting
                if signal_type in ["storm", "thunderstorm", "deteriorating", "storm_clearing"] and confidence >= 75:
                    severe_signals.append(confidence / 100.0)  # Convert to probability
                elif confidence >= 50:
                    routine_signals.append(confidence / 100.0)
            
            # Calculate combined confidence using noisy-OR for severe signals
            if severe_signals:
                # P = 1 - ∏(1 - p_i) for severe signals
                severe_combined = 1.0 - math.prod(1.0 - p for p in severe_signals)
                # Set minimum floor for severe signals
                final_confidence = max(severe_combined * 100, 75)  # At least 75% for severe
            elif routine_signals:
                # Weighted average for routine signals
                weights = [2.0 if signal_type in ["pressure_change", "dewpoint"] else 1.0 
                          for signal_type in confidence_scores.keys()]
                weighted_sum = sum(conf * weight for conf, weight in zip(routine_signals, weights[:len(routine_signals)]))
                weight_total = sum(weights[:len(routine_signals)])
                final_confidence = (weighted_sum / weight_total) * 100 if weight_total > 0 else 50
            else:
                final_confidence = 50
            
            # Apply confidence labels
            if final_confidence > 80:
                predictions.insert(0, "📊 High confidence forecast (>80%)")
            elif final_confidence > 60:
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
    
    def get_api_comparison(self):
        """Get comparison between local sensors and official weather data"""
        try:
            if not self.current_data:
                return {"error": "No local data available"}
            
            # Get official weather summary
            official_summary = self.api_service.get_weather_summary()
            if "error" in official_summary:
                return official_summary
            
            # Get detailed comparison
            comparison = self.api_service.compare_with_local(
                local_temp_f=self.current_data.get("temperature_f"),
                local_humidity=self.current_data.get("humidity"), 
                local_pressure_hpa=self.current_data.get("pressure_hpa")
            )
            
            # Combine for dashboard display
            result = {
                "official": official_summary,
                "comparison": comparison,
                "summary_status": self._get_overall_comparison_status(comparison)
            }
            
            return result
            
        except Exception as e:
            return {"error": f"API comparison failed: {str(e)}"}
    
    def _get_overall_comparison_status(self, comparison):
        """Get overall status from individual comparisons"""
        if "error" in comparison:
            return "unavailable"
        
        statuses = [comp.get("status", "unknown") for comp in comparison.get("comparisons", [])]
        
        if not statuses:
            return "no_data"
        elif all(status == "excellent" for status in statuses):
            return "excellent"  # All excellent
        elif all(status in ["excellent", "good"] for status in statuses):
            return "good"       # All good or better
        elif any(status == "check_calibration" for status in statuses):
            return "check_calibration"  # At least one needs calibration
        else:
            return "mixed"      # Mixed results
    
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
    """Get pressure trend data for specified hours (default 24)"""
    try:
        hours = int(request.args.get("hours", "24"))
        # Limit to reasonable range
        hours = max(1, min(hours, 168))  # 1 hour to 1 week
    except ValueError:
        hours = 24
    
    pressure_data = dashboard.data_service.get_pressure_history(hours=hours)
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


@app.route("/api/weather_comparison")
def api_weather_comparison():
    """Get comparison between local sensors and official weather data"""
    try:
        comparison = dashboard.get_api_comparison()
        return jsonify(comparison)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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