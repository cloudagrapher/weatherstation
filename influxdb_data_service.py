"""
InfluxDB Data Service for Weather Dashboard
Provides data access methods for the dashboard running on masterbox
"""

import math
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# Try to import configuration
try:
    from influxdb_config import INFLUX_HOST, INFLUX_PORT, INFLUX_ORG, INFLUX_BUCKET, INFLUX_TOKEN
except ImportError:
    raise ImportError("influxdb_config.py not found. Please configure your InfluxDB settings.")


class WeatherDataService:
    """Service to fetch weather data from InfluxDB"""
    
    def __init__(self):
        self.client = None
        self.query_api = None
        self.write_api = None
        self._connect()
    
    def _connect(self):
        """Initialize InfluxDB connection"""
        try:
            self.client = InfluxDBClient(
                url=f"http://{INFLUX_HOST}:{INFLUX_PORT}",
                token=INFLUX_TOKEN,
                org=INFLUX_ORG
            )
            self.query_api = self.client.query_api()
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
            print(f"Connected to InfluxDB at {INFLUX_HOST}:{INFLUX_PORT}")
        except Exception as e:
            print(f"Failed to connect to InfluxDB: {e}")
            raise
    
    def get_current_data(self) -> Optional[Dict[str, Any]]:
        """Get the most recent weather reading"""
        query = f'''
        from(bucket: "{INFLUX_BUCKET}")
          |> range(start: -24h)
          |> filter(fn: (r) => r["_measurement"] == "weather")
          |> filter(fn: (r) => r["location"] == "weatherbox")
          |> group(columns: ["_field"])
          |> last()
        '''
        
        try:
            tables = self.query_api.query(query, org=INFLUX_ORG)
            
            if not tables:
                return None
            
            # Collect the latest value for each field
            data = {}
            latest_time = None
            
            for table in tables:
                if table.records:
                    record = table.records[0]
                    field = record.values.get("_field")
                    value = record.values.get("_value")
                    timestamp = record.get_time()
                    
                    if field and value is not None:
                        data[field] = value
                        if latest_time is None or timestamp > latest_time:
                            latest_time = timestamp
            
            if data and latest_time:
                data["timestamp"] = latest_time.isoformat()
                return data
            
            return None
            
        except Exception as e:
            print(f"Error fetching current data: {e}")
            return None
    
    def get_historical_data(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get historical data for the specified number of hours"""
        query = f'''
        from(bucket: "{INFLUX_BUCKET}")
          |> range(start: -{hours}h)
          |> filter(fn: (r) => r["_measurement"] == "weather")
          |> filter(fn: (r) => r["location"] == "weatherbox")
          |> sort(columns: ["_time"])
        '''
        
        return self._execute_query_for_readings(query)
    
    def get_recent_data(self, hours: int = None, minutes: int = None) -> List[Dict[str, Any]]:
        """Get readings within the last N hours/minutes"""
        if minutes is not None:
            time_range = f"-{minutes}m"
        elif hours is not None:
            time_range = f"-{hours}h"
        else:
            time_range = "-3h"  # Default to 3 hours
        
        query = f'''
        from(bucket: "{INFLUX_BUCKET}")
          |> range(start: {time_range})
          |> filter(fn: (r) => r["_measurement"] == "weather")
          |> filter(fn: (r) => r["location"] == "weatherbox")
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
          |> sort(columns: ["_time"])
        '''
        
        return self._execute_query_for_readings(query)
    
    def get_pressure_history(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get pressure data for the specified hours"""
        query = f'''
        from(bucket: "{INFLUX_BUCKET}")
          |> range(start: -{hours}h)
          |> filter(fn: (r) => r["_measurement"] == "weather")
          |> filter(fn: (r) => r["location"] == "weatherbox")
          |> filter(fn: (r) => r["_field"] == "pressure_hpa")
          |> map(fn: (r) => ({{
            _time: r._time,
            timestamp: string(v: r._time),
            pressure_hpa: r._value
          }}))
          |> sort(columns: ["_time"])
        '''
        
        try:
            tables = self.query_api.query(query, org=INFLUX_ORG)
            
            if not tables:
                return []
            
            readings = []
            for record in tables[0].records:
                data = {
                    "timestamp": record.get_time().isoformat(),
                    "pressure_hpa": record.values.get("pressure_hpa")
                }
                readings.append(data)
            
            return readings
            
        except Exception as e:
            print(f"Error fetching pressure history: {e}")
            return []
    
    def get_week_history(self) -> List[Dict[str, Any]]:
        """Get 7-day historical data, sampled to reduce data points"""
        query = f'''
        from(bucket: "{INFLUX_BUCKET}")
          |> range(start: -7d)
          |> filter(fn: (r) => r["_measurement"] == "weather")
          |> filter(fn: (r) => r["location"] == "weatherbox")
          |> aggregateWindow(every: 15m, fn: mean, createEmpty: false)
          |> sort(columns: ["_time"])
        '''
        
        return self._execute_query_for_readings(query)
    
    def _execute_query_for_readings(self, query: str) -> List[Dict[str, Any]]:
        """Helper method to execute query and return cleaned readings"""
        try:
            tables = self.query_api.query(query, org=INFLUX_ORG)
            
            if not tables:
                return []
            
            # Group records by timestamp
            readings_by_time = {}
            
            for table in tables:
                for record in table.records:
                    timestamp = record.get_time().isoformat()
                    field = record.values.get("_field")
                    value = record.values.get("_value")
                    
                    if timestamp not in readings_by_time:
                        readings_by_time[timestamp] = {"timestamp": timestamp}
                    
                    if field and value is not None:
                        readings_by_time[timestamp][field] = value
            
            # Convert to list and sort by timestamp
            readings = list(readings_by_time.values())
            readings.sort(key=lambda x: x["timestamp"])
            
            # Filter out readings with insufficient data
            filtered_readings = []
            for reading in readings:
                if len(reading) > 1:  # Must have timestamp + at least one field
                    filtered_readings.append(reading)
            
            return filtered_readings
            
        except Exception as e:
            print(f"Error executing query: {e}")
            return []
    
    def get_daily_summary(self, date: datetime = None) -> Optional[Dict[str, Any]]:
        """Get today's temperature, humidity, and pressure range"""
        if date is None:
            date = datetime.now().date()
        
        start_time = datetime.combine(date, datetime.min.time())
        end_time = start_time + timedelta(days=1)
        
        # Get all data for the day
        query = f'''
        from(bucket: "{INFLUX_BUCKET}")
          |> range(start: {start_time.isoformat()}Z, stop: {end_time.isoformat()}Z)
          |> filter(fn: (r) => r["_measurement"] == "weather")
          |> filter(fn: (r) => r["location"] == "weatherbox")
        '''
        
        try:
            readings = self._execute_query_for_readings(query)
            
            if not readings:
                return None
            
            # Calculate summary from readings
            temps = [r["temperature_f"] for r in readings if "temperature_f" in r]
            humidities = [r["humidity"] for r in readings if "humidity" in r]
            pressures = [r["pressure_hpa"] for r in readings if "pressure_hpa" in r]
            
            summary = {
                "readings_count": len(readings)
            }
            
            if temps:
                summary["temp_high"] = max(temps)
                summary["temp_low"] = min(temps)
            
            if humidities:
                summary["humidity_high"] = max(humidities)
                summary["humidity_low"] = min(humidities)
            
            if pressures:
                summary["pressure_high"] = max(pressures)
                summary["pressure_low"] = min(pressures)
                summary["pressure_current"] = pressures[-1]  # Last reading
            
            return summary
            
        except Exception as e:
            print(f"Error fetching daily summary: {e}")
            return None
    
    def store_weather_event(self, event_type: str, intensity: str = None, notes: str = None, 
                           current_conditions: Dict[str, Any] = None) -> bool:
        """Store a tagged weather event in InfluxDB"""
        if not self.write_api:
            return False
        
        try:
            timestamp = datetime.now()
            
            # Create the main event point
            point = Point("weather_events") \
                .tag("location", "weatherbox") \
                .tag("event_type", event_type) \
                .tag("source", "user_tagged") \
                .field("event_type_value", event_type)
            
            if intensity:
                point.tag("intensity", intensity)
                point.field("intensity_value", intensity)
            
            if notes:
                point.field("notes", notes)
            
            # Add current weather conditions as fields if available
            if current_conditions:
                for key, value in current_conditions.items():
                    if key != "timestamp" and value is not None:
                        point.field(f"conditions_{key}", value)
            
            point.time(timestamp, WritePrecision.S)
            
            self.write_api.write(bucket=INFLUX_BUCKET, record=point)
            print(f"✓ Stored weather event: {event_type}")
            return True
            
        except Exception as e:
            print(f"Error storing weather event: {e}")
            return False
    
    def get_recent_weather_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent tagged weather events from InfluxDB"""
        query = f'''
        from(bucket: "{INFLUX_BUCKET}")
          |> range(start: -30d)
          |> filter(fn: (r) => r["_measurement"] == "weather_events")
          |> filter(fn: (r) => r["location"] == "weatherbox")
          |> sort(columns: ["_time"], desc: true)
          |> limit(n: {limit})
        '''
        
        try:
            tables = self.query_api.query(query, org=INFLUX_ORG)
            
            if not tables:
                return []
            
            # Group events by timestamp
            events_by_time = {}
            
            for table in tables:
                for record in table.records:
                    timestamp = record.get_time().isoformat()
                    field = record.values.get("_field")
                    value = record.values.get("_value")
                    
                    if timestamp not in events_by_time:
                        events_by_time[timestamp] = {
                            "timestamp": timestamp,
                            "event_type": record.values.get("event_type"),
                            "intensity": record.values.get("intensity"),
                            "conditions": {}
                        }
                    
                    # Store field values
                    if field == "event_type_value":
                        events_by_time[timestamp]["event_type"] = value
                    elif field == "intensity_value":
                        events_by_time[timestamp]["intensity"] = value
                    elif field == "notes":
                        events_by_time[timestamp]["notes"] = value
                    elif field and field.startswith("conditions_"):
                        condition_name = field.replace("conditions_", "")
                        events_by_time[timestamp]["conditions"][condition_name] = value
            
            # Convert to list and sort by timestamp (newest first)
            events = list(events_by_time.values())
            events.sort(key=lambda x: x["timestamp"], reverse=True)
            
            return events[:limit]
            
        except Exception as e:
            print(f"Error fetching weather events: {e}")
            return []
    
    def close(self):
        """Close the InfluxDB connection"""
        if self.client:
            self.client.close()