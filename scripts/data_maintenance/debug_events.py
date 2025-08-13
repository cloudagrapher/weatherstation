#!/usr/bin/env python3
"""
Debug script to see all data in the weather_events measurement
"""

import sys
import os

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
    client = InfluxDBClient(
        url=f"http://{INFLUX_HOST}:{INFLUX_PORT}", token=INFLUX_TOKEN, org=INFLUX_ORG
    )
    query_api = client.query_api()

    # Query ALL data in weather_events measurement
    query = f"""
    from(bucket: "{INFLUX_BUCKET}")
      |> range(start: -30d)
      |> filter(fn: (r) => r["_measurement"] == "weather_events")
      |> sort(columns: ["_time"], desc: false)
    """

    print("Querying ALL weather_events data...")
    tables = query_api.query(query, org=INFLUX_ORG)

    if not tables:
        print("No data found in weather_events measurement.")
        return

    print("All data in weather_events:")
    print("-" * 120)

    for table in tables:
        for record in table.records:
            print(f"Time: {record.get_time()}")
            print(f"Field: {record.values.get('_field')}")
            print(f"Value: {record.values.get('_value')}")
            print(f"Tags: {record.values}")
            print("-" * 60)

    client.close()


if __name__ == "__main__":
    main()
