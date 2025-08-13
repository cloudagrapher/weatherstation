"""
InfluxDB Data Service for Weather Dashboard
Provides data access methods for the dashboard running on masterbox
"""

import math
import pytz
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# Try to import configuration
try:
    from config.influxdb_config import (
        INFLUX_HOST,
        INFLUX_PORT,
        INFLUX_ORG,
        INFLUX_BUCKET,
        INFLUX_TOKEN,
    )
except ImportError:
    raise ImportError(
        "influxdb_config.py not found. Please configure your InfluxDB settings."
    )


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
                org=INFLUX_ORG,
            )
            self.query_api = self.client.query_api()
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
            print(f"Connected to InfluxDB at {INFLUX_HOST}:{INFLUX_PORT}")
        except Exception as e:
            print(f"Failed to connect to InfluxDB: {e}")
            raise

    def get_current_data(self) -> Optional[Dict[str, Any]]:
        """Get the most recent weather reading"""
        query = f"""
        from(bucket: "{INFLUX_BUCKET}")
          |> range(start: -24h)
          |> filter(fn: (r) => r["_measurement"] == "weather")
          |> filter(fn: (r) => r["location"] == "weatherbox")
          |> group(columns: ["_field"])
          |> last()
        """

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
                # Convert UTC timestamp to local time
                import pytz

                local_tz = pytz.timezone("America/New_York")
                if latest_time.tzinfo is None:
                    latest_time = pytz.utc.localize(latest_time)
                local_time = latest_time.astimezone(local_tz)
                data["timestamp"] = local_time.isoformat()
                return data

            return None

        except Exception as e:
            print(f"Error fetching current data: {e}")
            return None

    def get_historical_data(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get historical data for the specified number of hours"""
        query = f"""
        from(bucket: "{INFLUX_BUCKET}")
          |> range(start: -{hours}h)
          |> filter(fn: (r) => r["_measurement"] == "weather")
          |> filter(fn: (r) => r["location"] == "weatherbox")
          |> sort(columns: ["_time"])
        """

        return self._execute_query_for_readings(query)

    def get_recent_data(
        self, hours: int = None, minutes: int = None
    ) -> List[Dict[str, Any]]:
        """Get readings within the last N hours/minutes"""
        if minutes is not None:
            time_range = f"-{minutes}m"
        elif hours is not None:
            time_range = f"-{hours}h"
        else:
            time_range = "-3h"  # Default to 3 hours

        query = f"""
        from(bucket: "{INFLUX_BUCKET}")
          |> range(start: {time_range})
          |> filter(fn: (r) => r["_measurement"] == "weather")
          |> filter(fn: (r) => r["location"] == "weatherbox")
          |> sort(columns: ["_time"])
        """

        return self._execute_query_for_readings(query)

    def get_pressure_history(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get pressure data for the specified hours"""
        query = f"""
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
        """

        try:
            tables = self.query_api.query(query, org=INFLUX_ORG)

            if not tables:
                return []

            readings = []
            for record in tables[0].records:
                # Convert UTC timestamp to local time
                import pytz

                local_tz = pytz.timezone("America/New_York")
                timestamp = record.get_time()
                if timestamp.tzinfo is None:
                    timestamp = pytz.utc.localize(timestamp)
                local_time = timestamp.astimezone(local_tz)

                data = {
                    "timestamp": local_time.isoformat(),
                    "pressure_hpa": record.values.get("pressure_hpa"),
                }
                readings.append(data)

            return readings

        except Exception as e:
            print(f"Error fetching pressure history: {e}")
            return []

    def get_week_history(self) -> List[Dict[str, Any]]:
        """Get 7-day historical data, sampled to reduce data points"""
        query = f"""
        from(bucket: "{INFLUX_BUCKET}")
          |> range(start: -7d)
          |> filter(fn: (r) => r["_measurement"] == "weather")
          |> filter(fn: (r) => r["location"] == "weatherbox")
          |> aggregateWindow(every: 15m, fn: mean, createEmpty: false)
          |> sort(columns: ["_time"])
        """

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
                    # Convert UTC timestamp to local time
                    import pytz

                    local_tz = pytz.timezone("America/New_York")
                    timestamp_dt = record.get_time()
                    if timestamp_dt.tzinfo is None:
                        timestamp_dt = pytz.utc.localize(timestamp_dt)
                    local_time = timestamp_dt.astimezone(local_tz)
                    timestamp = local_time.isoformat()

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
        query = f"""
        from(bucket: "{INFLUX_BUCKET}")
          |> range(start: {start_time.isoformat()}Z, stop: {end_time.isoformat()}Z)
          |> filter(fn: (r) => r["_measurement"] == "weather")
          |> filter(fn: (r) => r["location"] == "weatherbox")
        """

        try:
            readings = self._execute_query_for_readings(query)

            if not readings:
                return None

            # Calculate summary from readings
            temps = [r["temperature_f"] for r in readings if "temperature_f" in r]
            humidities = [r["humidity"] for r in readings if "humidity" in r]
            pressures = [r["pressure_hpa"] for r in readings if "pressure_hpa" in r]

            summary = {"readings_count": len(readings)}

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

            # Calculate feels like high and low
            feels_like_temps = []
            for reading in readings:
                if "temperature_f" in reading and "humidity" in reading:
                    feels_like = self._calculate_feels_like(
                        reading["temperature_f"], reading["humidity"]
                    )
                    feels_like_temps.append(feels_like)

            if feels_like_temps:
                summary["feels_like_high"] = max(feels_like_temps)
                summary["feels_like_low"] = min(feels_like_temps)

            return summary

        except Exception as e:
            print(f"Error fetching daily summary: {e}")
            return None

    def store_weather_event(
        self,
        event_type: str,
        intensity: Optional[str] = None,
        notes: Optional[str] = None,
        current_conditions: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Store a tagged weather event in InfluxDB"""
        if not self.write_api:
            return False

        try:
            # Use local timezone for the timestamp
            local_tz = pytz.timezone("America/New_York")
            timestamp = datetime.now(local_tz)

            # Create the main event point
            point = (
                Point("weather_events")
                .tag("location", "weatherbox")
                .tag("event_type", event_type)
                .tag("source", "user_tagged")
                .field("event_type_value", event_type)
            )

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
        query = f"""
        from(bucket: "{INFLUX_BUCKET}")
          |> range(start: -30d)
          |> filter(fn: (r) => r["_measurement"] == "weather_events")
          |> filter(fn: (r) => r["location"] == "weatherbox")
          |> sort(columns: ["_time"], desc: true)
          |> limit(n: {limit})
        """

        try:
            tables = self.query_api.query(query, org=INFLUX_ORG)

            if not tables:
                return []

            # Group events by timestamp
            events_by_time = {}

            for table in tables:
                for record in table.records:
                    # Convert UTC timestamp to local time
                    import pytz

                    local_tz = pytz.timezone("America/New_York")
                    timestamp_dt = record.get_time()
                    if timestamp_dt.tzinfo is None:
                        timestamp_dt = pytz.utc.localize(timestamp_dt)
                    local_time = timestamp_dt.astimezone(local_tz)
                    timestamp = local_time.isoformat()

                    field = record.values.get("_field")
                    value = record.values.get("_value")

                    if timestamp not in events_by_time:
                        events_by_time[timestamp] = {
                            "timestamp": timestamp,
                            "event_type": record.values.get("event_type"),
                            "intensity": record.values.get("intensity"),
                            "conditions": {},
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

    def store_weather_predictions(
        self,
        predictions: List[str],
        current_conditions: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Store weather predictions in InfluxDB for historical analysis"""
        if not self.write_api or not predictions:
            return False

        try:
            import pytz

            eastern_tz = pytz.timezone("America/New_York")
            timestamp = datetime.now(eastern_tz)

            # Create a single point with all predictions
            point = (
                Point("weather_predictions")
                .tag("location", "weatherbox")
                .tag("source", "system_generated")
                .field("prediction_count", len(predictions))
            )

            # Store each prediction as a separate field
            for i, prediction in enumerate(predictions):
                point.field(f"prediction_{i}", prediction)

            # Add current weather conditions for later comparison
            if current_conditions:
                for key, value in current_conditions.items():
                    if key != "timestamp" and value is not None:
                        if key in [
                            "temperature_f",
                            "temperature_c",
                            "humidity",
                            "pressure_hpa",
                        ]:
                            point.field(f"conditions_{key}", value)

            point.time(timestamp, WritePrecision.S)

            self.write_api.write(bucket=INFLUX_BUCKET, record=point)
            return True

        except Exception as e:
            print(f"Error storing weather predictions: {e}")
            return False

    def get_historical_predictions(
        self, start_date: datetime, end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Get historical predictions for a date range"""
        if end_date is None:
            end_date = start_date + timedelta(days=1)

        query = f"""
        from(bucket: "{INFLUX_BUCKET}")
          |> range(start: {start_date.isoformat()}, stop: {end_date.isoformat()})
          |> filter(fn: (r) => r["_measurement"] == "weather_predictions")
          |> filter(fn: (r) => r["location"] == "weatherbox")
          |> sort(columns: ["_time"])
        """

        try:
            tables = self.query_api.query(query, org=INFLUX_ORG)

            if not tables:
                return []

            # Group predictions by timestamp
            predictions_by_time = {}

            for table in tables:
                for record in table.records:
                    # Convert UTC timestamp to local time
                    import pytz

                    local_tz = pytz.timezone("America/New_York")
                    timestamp_dt = record.get_time()
                    if timestamp_dt.tzinfo is None:
                        timestamp_dt = pytz.utc.localize(timestamp_dt)
                    local_time = timestamp_dt.astimezone(local_tz)
                    timestamp = local_time.isoformat()

                    field = record.values.get("_field")
                    value = record.values.get("_value")

                    if timestamp not in predictions_by_time:
                        predictions_by_time[timestamp] = {
                            "timestamp": timestamp,
                            "predictions": [],
                            "conditions": {},
                        }

                    # Store predictions and conditions
                    if (
                        field
                        and field.startswith("prediction_")
                        and isinstance(value, str)
                    ):
                        try:
                            pred_index = int(field.replace("prediction_", ""))
                            predictions_by_time[timestamp]["predictions"].append(
                                {"index": pred_index, "text": value}
                            )
                        except ValueError:
                            pass
                    elif field and field.startswith("conditions_"):
                        condition_name = field.replace("conditions_", "")
                        predictions_by_time[timestamp]["conditions"][
                            condition_name
                        ] = value

            # Sort predictions within each timestamp and convert to list
            result = []
            for pred_data in predictions_by_time.values():
                # Sort predictions by index
                pred_data["predictions"].sort(key=lambda x: x["index"])
                pred_data["predictions"] = [p["text"] for p in pred_data["predictions"]]
                result.append(pred_data)

            # Sort by timestamp
            result.sort(key=lambda x: x["timestamp"])
            return result

        except Exception as e:
            print(f"Error fetching historical predictions: {e}")
            return []

    def get_weather_analysis(
        self, start_date: datetime, end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get comprehensive weather analysis for a date range"""
        if end_date is None:
            end_date = start_date + timedelta(days=1)

        # Get weather data
        weather_query = f"""
        from(bucket: "{INFLUX_BUCKET}")
          |> range(start: {start_date.isoformat()}, stop: {end_date.isoformat()})
          |> filter(fn: (r) => r["_measurement"] == "weather")
          |> filter(fn: (r) => r["location"] == "weatherbox")
          |> aggregateWindow(every: 30m, fn: mean, createEmpty: false)
          |> sort(columns: ["_time"])
        """

        weather_data = self._execute_query_for_readings(weather_query)

        # Get predictions for the same period
        predictions = self.get_historical_predictions(start_date, end_date)

        # Get tagged events
        events_query = f"""
        from(bucket: "{INFLUX_BUCKET}")
          |> range(start: {start_date.isoformat()}, stop: {end_date.isoformat()})
          |> filter(fn: (r) => r["_measurement"] == "weather_events")
          |> filter(fn: (r) => r["location"] == "weatherbox")
          |> sort(columns: ["_time"])
        """

        try:
            tables = self.query_api.query(events_query, org=INFLUX_ORG)
            events = []

            if tables:
                events_by_time = {}
                for table in tables:
                    for record in table.records:
                        # Convert timestamp to local time
                        import pytz

                        local_tz = pytz.timezone("America/New_York")
                        timestamp_dt = record.get_time()
                        if timestamp_dt.tzinfo is None:
                            timestamp_dt = pytz.utc.localize(timestamp_dt)
                        local_time = timestamp_dt.astimezone(local_tz)
                        timestamp = local_time.isoformat()

                        if timestamp not in events_by_time:
                            events_by_time[timestamp] = {
                                "timestamp": timestamp,
                                "event_type": record.values.get("event_type"),
                                "intensity": record.values.get("intensity"),
                            }

                events = list(events_by_time.values())
                events.sort(key=lambda x: x["timestamp"])

        except Exception as e:
            print(f"Error fetching events: {e}")
            events = []

        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "weather_data": weather_data,
            "predictions": predictions,
            "events": events,
            "summary": self._generate_period_summary(weather_data, predictions, events),
        }

    def _generate_period_summary(
        self,
        weather_data: List[Dict[str, Any]],
        predictions: List[Dict[str, Any]],
        events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Generate summary statistics for a period"""
        if not weather_data:
            return {}

        temps = [r["temperature_f"] for r in weather_data if "temperature_f" in r]
        humidities = [r["humidity"] for r in weather_data if "humidity" in r]
        pressures = [r["pressure_hpa"] for r in weather_data if "pressure_hpa" in r]

        summary = {
            "reading_count": len(weather_data),
            "prediction_count": len(predictions),
            "event_count": len(events),
        }

        if temps:
            summary.update(
                {
                    "temp_high": max(temps),
                    "temp_low": min(temps),
                    "temp_avg": sum(temps) / len(temps),
                }
            )

        if humidities:
            summary.update(
                {
                    "humidity_high": max(humidities),
                    "humidity_low": min(humidities),
                    "humidity_avg": sum(humidities) / len(humidities),
                }
            )

        if pressures:
            summary.update(
                {
                    "pressure_high": max(pressures),
                    "pressure_low": min(pressures),
                    "pressure_avg": sum(pressures) / len(pressures),
                }
            )

        return summary

    def _calculate_feels_like(self, temp_f, humidity, wind_mph=0):
        """Calculate 'feels like' temperature based on conditions"""
        temp_c = (temp_f - 32) * 5 / 9

        # Hot weather: Use Heat Index
        if temp_f >= 80 and humidity >= 40:
            return self._heat_index(temp_f, humidity)

        # Cold weather with wind: Use Wind Chill
        elif temp_f <= 50 and wind_mph >= 3:
            return self._wind_chill(temp_f, wind_mph)

        # Moderate conditions: Use simplified apparent temperature
        else:
            return self._apparent_temperature(
                temp_c, humidity, wind_mph * 0.44704
            )  # mph to m/s

    def _heat_index(self, temp_f, humidity):
        """Calculate heat index for hot, humid conditions"""
        if temp_f < 80 or humidity < 40:
            return temp_f

        # Full Rothfusz regression equation
        hi = -42.379 + 2.04901523 * temp_f + 10.14333127 * humidity
        hi += -0.22475541 * temp_f * humidity - 6.83783e-3 * temp_f**2
        hi += -5.481717e-2 * humidity**2 + 1.22874e-3 * temp_f**2 * humidity
        hi += 8.5282e-4 * temp_f * humidity**2 - 1.99e-6 * temp_f**2 * humidity**2

        # Adjustments for extreme conditions
        if humidity < 13 and 80 <= temp_f <= 112:
            hi -= ((13 - humidity) / 4) * math.sqrt((17 - abs(temp_f - 95.0)) / 17)
        elif humidity > 85 and 80 <= temp_f <= 87:
            hi += ((humidity - 85) / 10) * ((87 - temp_f) / 5)

        return round(hi, 1)

    def _wind_chill(self, temp_f, wind_mph):
        """Calculate wind chill for cold, windy conditions"""
        if temp_f > 50 or wind_mph < 3:
            return temp_f

        wc = 35.74 + 0.6215 * temp_f - 35.75 * (wind_mph**0.16)
        wc += 0.4275 * temp_f * (wind_mph**0.16)

        return round(wc, 1)

    def _apparent_temperature(self, temp_c, humidity, wind_ms):
        """Calculate apparent temperature for moderate conditions"""
        # Vapor pressure in hPa
        e = (humidity / 100) * 6.105 * math.exp(17.27 * temp_c / (237.7 + temp_c))

        # Apparent temperature
        at = temp_c + 0.33 * e - 0.7 * wind_ms - 4.0

        # Convert back to Fahrenheit
        return round(at * 9 / 5 + 32, 1)

    def close(self):
        """Close the InfluxDB connection"""
        if self.client:
            self.client.close()
