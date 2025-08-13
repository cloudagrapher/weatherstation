#!/usr/bin/env python3
"""
Script to fix weather event timestamps by adding 4 hours to correct UTC -> EDT offset
"""

import sys
import os
import pytz
from datetime import datetime, timedelta
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_config import INFLUX_HOST, INFLUX_PORT, INFLUX_ORG, INFLUX_BUCKET, INFLUX_TOKEN

def main():
    print("Connecting to InfluxDB...")
    client = InfluxDBClient(url=f"http://{INFLUX_HOST}:{INFLUX_PORT}", token=INFLUX_TOKEN, org=INFLUX_ORG)
    query_api = client.query_api()
    write_api = client.write_api(write_options=SYNCHRONOUS)
    
    # Query all weather events
    query = f'''
    from(bucket: "{INFLUX_BUCKET}")
      |> range(start: -30d)
      |> filter(fn: (r) => r["_measurement"] == "weather_events")
      |> filter(fn: (r) => r["location"] == "weatherbox")
      |> sort(columns: ["_time"], desc: false)
    '''
    
    print("Querying existing weather events...")
    tables = query_api.query(query, org=INFLUX_ORG)
    
    if not tables:
        print("No weather events found.")
        return
    
    # Collect all events by timestamp
    events_by_time = {}
    original_times = set()
    
    for table in tables:
        for record in table.records:
            timestamp = record.get_time()
            original_times.add(timestamp)
            
            # Check if this timestamp looks like UTC (no timezone offset)
            # We'll assume any timestamp without explicit timezone info was stored as UTC
            if timestamp.tzinfo is None or timestamp.utcoffset() == timedelta(0):
                # This is likely a UTC timestamp that needs fixing
                field = record.values.get("_field")
                value = record.values.get("_value")
                
                if timestamp not in events_by_time:
                    events_by_time[timestamp] = {
                        "timestamp": timestamp,
                        "event_type": record.values.get("event_type"),
                        "intensity": record.values.get("intensity"),
                        "fields": {}
                    }
                
                events_by_time[timestamp]["fields"][field] = value
    
    if not events_by_time:
        print("No UTC timestamps found that need fixing.")
        return
    
    print(f"Found {len(events_by_time)} events with UTC timestamps to fix:")
    
    eastern_tz = pytz.timezone('America/New_York')
    
    for timestamp, event_data in events_by_time.items():
        # Convert UTC to Eastern Time (add 4 hours for EDT, 5 for EST)
        utc_time = timestamp if timestamp.tzinfo else pytz.utc.localize(timestamp)
        eastern_time = utc_time.astimezone(eastern_tz)
        
        print(f"  {utc_time} -> {eastern_time}")
        
        # Create new event with corrected timestamp
        point = Point("weather_events") \
            .tag("location", "weatherbox") \
            .tag("source", "user_tagged")
        
        if event_data["event_type"]:
            point.tag("event_type", event_data["event_type"])
        if event_data["intensity"]:
            point.tag("intensity", event_data["intensity"])
        
        # Add all fields
        for field, value in event_data["fields"].items():
            point.field(field, value)
        
        # Set the corrected timestamp
        point.time(eastern_time, WritePrecision.S)
        
        # Write the corrected event
        write_api.write(bucket=INFLUX_BUCKET, record=point)
    
    print(f"\\n✓ Created {len(events_by_time)} corrected events")
    
    # Now delete the original UTC events
    print("\\nDeleting original UTC events...")
    for timestamp in original_times:
        if timestamp.tzinfo is None or timestamp.utcoffset() == timedelta(0):
            # Delete the original UTC event
            start_time = timestamp - timedelta(seconds=1)
            stop_time = timestamp + timedelta(seconds=1)
            
            delete_api = client.delete_api()
            delete_api.delete(
                start_time,
                stop_time,
                '_measurement="weather_events" AND location="weatherbox"',
                bucket=INFLUX_BUCKET,
                org=INFLUX_ORG
            )
    
    print("✓ Cleanup completed!")
    client.close()

if __name__ == "__main__":
    main()