#!/usr/bin/env python3
"""
Script to fix weather event timestamps by adding 4 hours to correct UTC -> EDT offset
This assumes all existing events were incorrectly stored in UTC when they should have been EDT
"""

import sys
import os
import pytz
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_config import (
    INFLUX_HOST,
    INFLUX_PORT,
    INFLUX_ORG,
    INFLUX_BUCKET,
    INFLUX_TOKEN,
)


def main():
    print("🔧 Fixing weather event timestamps...")
    print("This will add 4 hours to all existing events to correct UTC -> EDT offset")

    response = input("Continue? (y/N): ")
    if response.lower() != "y":
        print("Cancelled.")
        return

    client = InfluxDBClient(
        url=f"http://{INFLUX_HOST}:{INFLUX_PORT}", token=INFLUX_TOKEN, org=INFLUX_ORG
    )
    query_api = client.query_api()
    write_api = client.write_api(write_options=SYNCHRONOUS)
    delete_api = client.delete_api()

    # Query all weather events
    query = f"""
    from(bucket: "{INFLUX_BUCKET}")
      |> range(start: -30d)
      |> filter(fn: (r) => r["_measurement"] == "weather_events")
      |> filter(fn: (r) => r["location"] == "weatherbox")
      |> sort(columns: ["_time"], desc: false)
    """

    print("📊 Querying existing weather events...")
    tables = query_api.query(query, org=INFLUX_ORG)

    if not tables:
        print("No weather events found.")
        return

    # Collect all events by timestamp
    events_by_time = {}
    timestamps_to_delete = set()

    for table in tables:
        for record in table.records:
            timestamp = record.get_time()
            timestamps_to_delete.add(timestamp)

            field = record.values.get("_field")
            value = record.values.get("_value")

            if timestamp not in events_by_time:
                events_by_time[timestamp] = {
                    "timestamp": timestamp,
                    "event_type": record.values.get("event_type"),
                    "intensity": record.values.get("intensity"),
                    "fields": {},
                }

            events_by_time[timestamp]["fields"][field] = value

    print(f"Found {len(events_by_time)} events to fix")

    eastern_tz = pytz.timezone("America/New_York")

    print("\\n📝 Creating corrected events...")
    for timestamp, event_data in events_by_time.items():
        # Add 4 hours to the UTC timestamp (EDT offset)
        corrected_time = timestamp + timedelta(hours=4)
        corrected_time_local = corrected_time.replace(tzinfo=eastern_tz)

        print(f"  {timestamp} -> {corrected_time_local}")

        # Create new event with corrected timestamp
        point = (
            Point("weather_events")
            .tag("location", "weatherbox")
            .tag("source", "user_tagged")
        )

        if event_data["event_type"]:
            point.tag("event_type", event_data["event_type"])
        if event_data["intensity"]:
            point.tag("intensity", event_data["intensity"])

        # Add all fields
        for field, value in event_data["fields"].items():
            if value is not None:
                point.field(field, value)

        # Set the corrected timestamp
        point.time(corrected_time_local, WritePrecision.S)

        # Write the corrected event
        write_api.write(bucket=INFLUX_BUCKET, record=point)

    print(f"\\n✅ Created {len(events_by_time)} corrected events")

    # Delete the original events
    print("\\n🗑️  Deleting original events...")
    for timestamp in timestamps_to_delete:
        start_time = timestamp - timedelta(seconds=1)
        stop_time = timestamp + timedelta(seconds=1)

        delete_api.delete(
            start_time,
            stop_time,
            '_measurement="weather_events" AND location="weatherbox"',
            bucket=INFLUX_BUCKET,
            org=INFLUX_ORG,
        )

    print("\\n🎉 Timestamp fix completed!")
    print("All weather events now have correct local timestamps.")

    client.close()


if __name__ == "__main__":
    main()
