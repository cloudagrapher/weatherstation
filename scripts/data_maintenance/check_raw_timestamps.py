#!/usr/bin/env python3
"""
Script to check raw timestamps in InfluxDB weather events
"""

import sys
import os
import pytz
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from influxdb_client import InfluxDBClient
from influxdb_config import (
    INFLUX_HOST,
    INFLUX_PORT,
    INFLUX_ORG,
    INFLUX_BUCKET,
    INFLUX_TOKEN,
)


def main():
    print("Connecting to InfluxDB...")
    client = InfluxDBClient(
        url=f"http://{INFLUX_HOST}:{INFLUX_PORT}", token=INFLUX_TOKEN, org=INFLUX_ORG
    )
    query_api = client.query_api()

    # Query all weather events with raw timestamps
    query = f"""
    from(bucket: "{INFLUX_BUCKET}")
      |> range(start: -30d)
      |> filter(fn: (r) => r["_measurement"] == "weather_events")
      |> filter(fn: (r) => r["location"] == "weatherbox")
      |> filter(fn: (r) => r["_field"] == "event_type_value")
      |> sort(columns: ["_time"], desc: false)
    """

    print("Querying weather events...")
    tables = query_api.query(query, org=INFLUX_ORG)

    if not tables:
        print("No weather events found.")
        return

    print("Raw timestamps from InfluxDB:")
    print("-" * 80)

    eastern_tz = pytz.timezone("America/New_York")
    now_local = datetime.now(eastern_tz)
    print(f"Current local time: {now_local}")
    print()

    for table in tables:
        for record in table.records:
            raw_time = record.get_time()
            event_type = record.values.get("_value")

            # Show the raw timestamp as stored in InfluxDB
            print(f"Event: {event_type}")
            print(f"  Raw timestamp: {raw_time} (tzinfo: {raw_time.tzinfo})")

            # Convert to local timezone for comparison
            if raw_time.tzinfo is None:
                utc_time = pytz.utc.localize(raw_time)
            else:
                utc_time = raw_time.astimezone(pytz.utc)

            local_time = utc_time.astimezone(eastern_tz)
            print(f"  As local time: {local_time}")

            # Check if this looks like it was 4 hours off
            time_diff = now_local - local_time
            print(f"  Hours ago: {time_diff.total_seconds() / 3600:.1f}")
            print()

    client.close()


if __name__ == "__main__":
    main()
