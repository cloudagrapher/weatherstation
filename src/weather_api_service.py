#!/home/masterbox/weatherstation/.venv/bin/python
"""
Weather API Service
Fetches official weather data from OpenWeatherMap One Call API 3.0 for comparison with local sensors
Provides sanity checking and additional context for local predictions
"""

import requests
import json
from datetime import datetime, timedelta
from typing import Dict, Optional
import time


class WeatherAPIService:
    """Service to fetch and process official weather data from OpenWeatherMap"""

    def __init__(self, lat=33.8888, lon=-84.5095):  # Smyrna, GA coordinates
        self.lat = lat
        self.lon = lon
        self.last_fetch = None
        self.cache_duration = 300  # 5 minutes cache
        self._cached_data = None
        self.api_key = "8bae038ea5195f275f833540bf41750a"
        self.base_url = "https://api.openweathermap.org/data/3.0/onecall"

    def _fetch_openweather_data(self) -> Optional[Dict]:
        """Fetch current weather data from OpenWeatherMap One Call API 3.0"""
        try:
            params = {
                'lat': self.lat,
                'lon': self.lon,
                'appid': self.api_key,
                'units': 'imperial',  # Get temperature in Fahrenheit
                'exclude': 'minutely,hourly,daily,alerts'  # Only get current weather
            }
            
            response = requests.get(self.base_url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"OpenWeatherMap API returned status {response.status_code}")
                if response.status_code == 401:
                    print("Check your API key")
                return None

        except Exception as e:
            print(f"Error fetching OpenWeatherMap data: {e}")
            return None

    def get_official_weather(self, force_refresh=False) -> Optional[Dict]:
        """Get official weather data with caching"""
        # Check cache first
        if (
            not force_refresh
            and self._cached_data
            and self.last_fetch
            and (datetime.now() - self.last_fetch).total_seconds() < self.cache_duration
        ):
            return self._cached_data

        # Fetch fresh data
        obs_data = self._fetch_openweather_data()
        if not obs_data:
            return self._cached_data  # Return cached data if fetch fails

        try:
            current = obs_data["current"]

            # Extract data from OpenWeatherMap format
            result = {
                "source": "OpenWeatherMap",
                "timestamp": datetime.fromtimestamp(current.get("dt", 0)).isoformat(),
                "temperature_c": None,
                "temperature_f": None,
                "feels_like_f": None,
                "humidity": None,
                "pressure_hpa": None,
                "pressure_mb": None,
                "wind_speed_mph": None,
                "wind_direction": None,
                "visibility_miles": None,
                "weather_description": None,
                "raw_data": current,  # Store for debugging
            }

            # Temperature (already in Fahrenheit due to units=imperial)
            if current.get("temp") is not None:
                temp_f = current["temp"]
                result["temperature_f"] = round(temp_f, 1)
                result["temperature_c"] = round((temp_f - 32) * 5 / 9, 1)

            # Feels like temperature (already in Fahrenheit due to units=imperial)
            if current.get("feels_like") is not None:
                result["feels_like_f"] = round(current["feels_like"], 1)

            # Humidity
            if current.get("humidity") is not None:
                result["humidity"] = round(current["humidity"], 1)

            # Pressure (already in hPa)
            if current.get("pressure") is not None:
                result["pressure_hpa"] = round(current["pressure"], 1)
                result["pressure_mb"] = round(current["pressure"], 1)  # Same as hPa

            # Wind (already in mph due to units=imperial)
            if current.get("wind_speed") is not None:
                result["wind_speed_mph"] = round(current["wind_speed"], 1)

            if current.get("wind_deg") is not None:
                result["wind_direction"] = current["wind_deg"]

            # Visibility (convert from meters to miles)
            if current.get("visibility") is not None:
                vis_m = current["visibility"]
                result["visibility_miles"] = round(vis_m * 0.000621371, 1)

            # Weather description
            if current.get("weather") and len(current["weather"]) > 0:
                weather = current["weather"][0]
                result["weather_description"] = weather.get("description", "").title()

            # Cache the result
            self._cached_data = result
            self.last_fetch = datetime.now()

            return result

        except Exception as e:
            print(f"Error processing OpenWeatherMap data: {e}")
            return None

    def compare_with_local(
        self, local_temp_f=None, local_humidity=None, local_pressure_hpa=None
    ) -> Dict:
        """Compare local readings with official weather data"""
        official = self.get_official_weather()
        if not official:
            return {"error": "No official data available for comparison"}

        comparison = {
            "official_source": f"OpenWeatherMap ({self.lat:.4f}, {self.lon:.4f})",
            "official_time": official.get("timestamp"),
            "comparisons": [],
        }

        # Temperature comparison
        if local_temp_f is not None and official.get("temperature_f") is not None:
            diff = local_temp_f - official["temperature_f"]
            comparison["comparisons"].append(
                {
                    "parameter": "Temperature",
                    "local": f"{local_temp_f:.1f}°F",
                    "official": f"{official['temperature_f']:.1f}°F",
                    "difference": f"{diff:+.1f}°F",
                    "status": self._get_difference_status(
                        abs(diff), [2, 5]
                    ),  # Good <2°F, OK <5°F
                }
            )

        # Humidity comparison
        if local_humidity is not None and official.get("humidity") is not None:
            diff = local_humidity - official["humidity"]
            comparison["comparisons"].append(
                {
                    "parameter": "Humidity",
                    "local": f"{local_humidity:.1f}%",
                    "official": f"{official['humidity']:.1f}%",
                    "difference": f"{diff:+.1f}%",
                    "status": self._get_difference_status(
                        abs(diff), [5, 10]
                    ),  # Good <5%, OK <10%
                }
            )

        # Pressure comparison
        if local_pressure_hpa is not None and official.get("pressure_hpa") is not None:
            diff = local_pressure_hpa - official["pressure_hpa"]
            comparison["comparisons"].append(
                {
                    "parameter": "Pressure",
                    "local": f"{local_pressure_hpa:.1f} hPa",
                    "official": f"{official['pressure_hpa']:.1f} hPa",
                    "difference": f"{diff:+.1f} hPa",
                    "status": self._get_difference_status(
                        abs(diff), [3, 7]
                    ),  # Good <3hPa, OK <7hPa
                }
            )

        return comparison

    def _get_difference_status(self, abs_diff, thresholds):
        """Get status based on difference thresholds"""
        if abs_diff <= thresholds[0]:
            return "excellent"
        elif abs_diff <= thresholds[1]:
            return "good"
        else:
            return "check_calibration"

    def get_weather_summary(self) -> Dict:
        """Get a summary suitable for dashboard display"""
        official = self.get_official_weather()
        if not official:
            return {"error": "Official weather data unavailable"}

        summary = {
            "source": "OpenWeatherMap",
            "location": f"{self.lat:.4f}, {self.lon:.4f}",
            "timestamp": official.get("timestamp"),
            "conditions": official.get("weather_description", "N/A"),
            "temperature_f": official.get("temperature_f"),
            "feels_like_f": official.get("feels_like_f"),
            "humidity": official.get("humidity"),
            "pressure_hpa": official.get("pressure_hpa"),
            "wind_speed_mph": official.get("wind_speed_mph"),
            "wind_direction": official.get("wind_direction"),
            "visibility_miles": official.get("visibility_miles"),
        }

        # Add human-readable timestamp
        if official.get("timestamp"):
            try:
                dt = datetime.fromisoformat(
                    official["timestamp"].replace("Z", "+00:00")
                )
                summary["time_local"] = dt.strftime("%I:%M %p")
                summary["age_minutes"] = int(
                    (datetime.now().astimezone() - dt).total_seconds() / 60
                )
            except:
                pass

        return summary


# Utility function for testing
def test_api_service():
    """Test the API service"""
    print("🌤️  Testing OpenWeatherMap API Service")
    print("=" * 50)

    service = WeatherAPIService()

    # Test basic fetch
    official = service.get_official_weather()
    if official:
        print(
            f"✅ Successfully fetched data from OpenWeatherMap"
        )
        print(f"   Temperature: {official.get('temperature_f', 'N/A')}°F")
        print(f"   Humidity: {official.get('humidity', 'N/A')}%")
        print(f"   Pressure: {official.get('pressure_hpa', 'N/A')} hPa")
        print(f"   Conditions: {official.get('weather_description', 'N/A')}")
        print(f"   Wind: {official.get('wind_speed_mph', 'N/A')} mph")

        # Test comparison with dummy local data
        comparison = service.compare_with_local(
            local_temp_f=78.0, local_humidity=85.0, local_pressure_hpa=1015.0
        )

        print("\n📊 Sample Comparison:")
        for comp in comparison.get("comparisons", []):
            print(
                f"   {comp['parameter']}: {comp['local']} vs {comp['official']} ({comp['difference']}) - {comp['status']}"
            )
    else:
        print("❌ Failed to fetch official weather data")


if __name__ == "__main__":
    test_api_service()
