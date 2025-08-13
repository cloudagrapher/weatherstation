#!/home/masterbox/weatherstation/.venv/bin/python
"""
Weather API Service
Fetches official weather data from National Weather Service for comparison with local sensors
Provides sanity checking and additional context for local predictions
"""

import requests
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import time

class WeatherAPIService:
    """Service to fetch and process official weather data"""
    
    def __init__(self, lat=33.8738, lon=-84.5157):  # Smyrna, GA coordinates
        self.lat = lat
        self.lon = lon
        self.station_id = None
        self.station_name = None
        self.last_fetch = None
        self.cache_duration = 300  # 5 minutes cache
        self._cached_data = None
    
    def _get_nearest_station(self) -> Tuple[Optional[str], Optional[str]]:
        """Find the nearest NWS weather station"""
        try:
            # Get point data to find nearest station
            url = f"https://api.weather.gov/points/{self.lat},{self.lon}"
            headers = {'User-Agent': 'WeatherStation-Smyrna-GA (contact@example.com)'}
            
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                station_url = data['properties']['observationStations']
                
                # Get stations
                stations_response = requests.get(station_url, headers=headers, timeout=10)
                if stations_response.status_code == 200:
                    stations = stations_response.json()
                    if stations['features']:
                        station_id = stations['features'][0]['properties']['stationIdentifier']
                        station_name = stations['features'][0]['properties']['name']
                        return station_id, station_name
            
            return None, None
        except Exception as e:
            print(f"Error finding NWS station: {e}")
            return None, None
    
    def _fetch_nws_observation(self) -> Optional[Dict]:
        """Fetch current observation from NWS"""
        try:
            # Get station if we don't have it
            if not self.station_id:
                self.station_id, self.station_name = self._get_nearest_station()
                if not self.station_id:
                    return None
            
            # Get latest observations
            url = f"https://api.weather.gov/stations/{self.station_id}/observations/latest"
            headers = {'User-Agent': 'WeatherStation-Smyrna-GA (contact@example.com)'}
            
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"NWS API returned status {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Error fetching NWS observation: {e}")
            return None
    
    def get_official_weather(self, force_refresh=False) -> Optional[Dict]:
        """Get official weather data with caching"""
        # Check cache first
        if (not force_refresh and 
            self._cached_data and 
            self.last_fetch and 
            (datetime.now() - self.last_fetch).total_seconds() < self.cache_duration):
            return self._cached_data
        
        # Fetch fresh data
        obs_data = self._fetch_nws_observation()
        if not obs_data:
            return self._cached_data  # Return cached data if fetch fails
        
        try:
            props = obs_data['properties']
            
            # Extract data with null checks
            result = {
                'station_id': self.station_id,
                'station_name': self.station_name,
                'timestamp': props.get('timestamp'),
                'temperature_c': None,
                'temperature_f': None,
                'humidity': None,
                'pressure_hpa': None,
                'pressure_mb': None,
                'wind_speed_mph': None,
                'wind_direction': None,
                'visibility_miles': None,
                'weather_description': None,
                'raw_data': props  # Store for debugging
            }
            
            # Temperature
            if props.get('temperature', {}).get('value') is not None:
                temp_c = props['temperature']['value']
                result['temperature_c'] = round(temp_c, 1)
                result['temperature_f'] = round((temp_c * 9/5) + 32, 1)
            
            # Humidity
            if props.get('relativeHumidity', {}).get('value') is not None:
                result['humidity'] = round(props['relativeHumidity']['value'], 1)
            
            # Pressure (convert from Pa to hPa)
            if props.get('barometricPressure', {}).get('value') is not None:
                pressure_pa = props['barometricPressure']['value']
                pressure_hpa = pressure_pa / 100
                result['pressure_hpa'] = round(pressure_hpa, 1)
                result['pressure_mb'] = round(pressure_hpa, 1)  # Same as hPa
            
            # Wind
            if props.get('windSpeed', {}).get('value') is not None:
                wind_ms = props['windSpeed']['value']
                result['wind_speed_mph'] = round(wind_ms * 2.237, 1) if wind_ms else 0
            
            if props.get('windDirection', {}).get('value') is not None:
                result['wind_direction'] = props['windDirection']['value']
            
            # Visibility
            if props.get('visibility', {}).get('value') is not None:
                vis_m = props['visibility']['value']
                result['visibility_miles'] = round(vis_m * 0.000621371, 1)
            
            # Weather description
            if props.get('textDescription'):
                result['weather_description'] = props['textDescription']
            
            # Cache the result
            self._cached_data = result
            self.last_fetch = datetime.now()
            
            return result
            
        except Exception as e:
            print(f"Error processing NWS data: {e}")
            return None
    
    def compare_with_local(self, local_temp_f=None, local_humidity=None, local_pressure_hpa=None) -> Dict:
        """Compare local readings with official weather data"""
        official = self.get_official_weather()
        if not official:
            return {"error": "No official data available for comparison"}
        
        comparison = {
            'official_station': f"{official.get('station_name', 'Unknown')} ({official.get('station_id', 'N/A')})",
            'official_time': official.get('timestamp'),
            'comparisons': []
        }
        
        # Temperature comparison
        if local_temp_f is not None and official.get('temperature_f') is not None:
            diff = local_temp_f - official['temperature_f']
            comparison['comparisons'].append({
                'parameter': 'Temperature',
                'local': f"{local_temp_f:.1f}°F",
                'official': f"{official['temperature_f']:.1f}°F", 
                'difference': f"{diff:+.1f}°F",
                'status': self._get_difference_status(abs(diff), [2, 5])  # Good <2°F, OK <5°F
            })
        
        # Humidity comparison  
        if local_humidity is not None and official.get('humidity') is not None:
            diff = local_humidity - official['humidity']
            comparison['comparisons'].append({
                'parameter': 'Humidity',
                'local': f"{local_humidity:.1f}%",
                'official': f"{official['humidity']:.1f}%",
                'difference': f"{diff:+.1f}%", 
                'status': self._get_difference_status(abs(diff), [5, 10])  # Good <5%, OK <10%
            })
        
        # Pressure comparison
        if local_pressure_hpa is not None and official.get('pressure_hpa') is not None:
            diff = local_pressure_hpa - official['pressure_hpa']
            comparison['comparisons'].append({
                'parameter': 'Pressure',
                'local': f"{local_pressure_hpa:.1f} hPa",
                'official': f"{official['pressure_hpa']:.1f} hPa",
                'difference': f"{diff:+.1f} hPa",
                'status': self._get_difference_status(abs(diff), [3, 7])  # Good <3hPa, OK <7hPa
            })
        
        return comparison
    
    def _get_difference_status(self, abs_diff, thresholds):
        """Get status based on difference thresholds"""
        if abs_diff <= thresholds[0]:
            return 'excellent'
        elif abs_diff <= thresholds[1]:
            return 'good' 
        else:
            return 'check_calibration'
    
    def get_weather_summary(self) -> Dict:
        """Get a summary suitable for dashboard display"""
        official = self.get_official_weather()
        if not official:
            return {"error": "Official weather data unavailable"}
        
        summary = {
            'source': f"NWS {official.get('station_id', 'N/A')}",
            'station_name': official.get('station_name', 'Unknown Station'),
            'timestamp': official.get('timestamp'),
            'conditions': official.get('weather_description', 'N/A'),
            'temperature_f': official.get('temperature_f'),
            'humidity': official.get('humidity'),
            'pressure_hpa': official.get('pressure_hpa'),
            'wind_speed_mph': official.get('wind_speed_mph'),
            'wind_direction': official.get('wind_direction'),
            'visibility_miles': official.get('visibility_miles')
        }
        
        # Add human-readable timestamp
        if official.get('timestamp'):
            try:
                dt = datetime.fromisoformat(official['timestamp'].replace('Z', '+00:00'))
                summary['time_local'] = dt.strftime('%I:%M %p')
                summary['age_minutes'] = int((datetime.now().astimezone() - dt).total_seconds() / 60)
            except:
                pass
        
        return summary

# Utility function for testing
def test_api_service():
    """Test the API service"""
    print("🌤️  Testing Weather API Service")
    print("=" * 50)
    
    service = WeatherAPIService()
    
    # Test basic fetch
    official = service.get_official_weather()
    if official:
        print(f"✅ Successfully fetched data from {official['station_name']} ({official['station_id']})")
        print(f"   Temperature: {official.get('temperature_f', 'N/A')}°F")
        print(f"   Humidity: {official.get('humidity', 'N/A')}%")
        print(f"   Pressure: {official.get('pressure_hpa', 'N/A')} hPa")
        print(f"   Conditions: {official.get('weather_description', 'N/A')}")
        
        # Test comparison with dummy local data
        comparison = service.compare_with_local(
            local_temp_f=78.0,
            local_humidity=85.0, 
            local_pressure_hpa=1015.0
        )
        
        print("\n📊 Sample Comparison:")
        for comp in comparison.get('comparisons', []):
            print(f"   {comp['parameter']}: {comp['local']} vs {comp['official']} ({comp['difference']}) - {comp['status']}")
    else:
        print("❌ Failed to fetch official weather data")

if __name__ == "__main__":
    test_api_service()