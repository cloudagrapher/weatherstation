#!/home/masterbox/weatherstation/.venv/bin/python
"""
Fix Historical Timestamps in InfluxDB
Corrects timezone issues in existing weather data by adding 4 hours to all timestamps
before the timezone fix was implemented.
"""

import pytz
from datetime import datetime, timedelta
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.client.delete_api import DeleteApi

# Import configuration
from influxdb_config import (
    INFLUX_HOST,
    INFLUX_PORT,
    INFLUX_ORG,
    INFLUX_BUCKET,
    INFLUX_TOKEN,
)

# Cutoff time - when we fixed the timezone issue
# Data before this needs to be corrected (add 4 hours)
TIMEZONE_FIX_TIME = datetime(2025, 8, 12, 12, 42, 0)  # When we fixed weatherbox
TIMEZONE_FIX_TIME = pytz.timezone("America/New_York").localize(TIMEZONE_FIX_TIME)


def get_influx_client():
    """Initialize InfluxDB client"""
    return InfluxDBClient(
        url=f"http://{INFLUX_HOST}:{INFLUX_PORT}", token=INFLUX_TOKEN, org=INFLUX_ORG
    )


def get_incorrect_data(client):
    """Get all weather data stored before the timezone fix"""
    query = f"""
    from(bucket: "{INFLUX_BUCKET}")
      |> range(start: -7d, stop: {TIMEZONE_FIX_TIME.isoformat()})
      |> filter(fn: (r) => r["_measurement"] == "weather")
      |> filter(fn: (r) => r["location"] == "weatherbox")
      |> sort(columns: ["_time"])
    """

    query_api = client.query_api()
    tables = query_api.query(query, org=INFLUX_ORG)

    # Group records by timestamp
    readings_by_time = {}

    for table in tables:
        for record in table.records:
            timestamp = record.get_time()
            field = record.values.get("_field")
            value = record.values.get("_value")

            # Skip if no field or value
            if not field or value is None:
                continue

            timestamp_key = timestamp.isoformat()
            if timestamp_key not in readings_by_time:
                readings_by_time[timestamp_key] = {
                    "original_timestamp": timestamp,
                    "fields": {},
                }

            readings_by_time[timestamp_key]["fields"][field] = value

    return list(readings_by_time.values())


def fix_timestamps_and_rewrite(client, incorrect_data):
    """Fix timestamps and rewrite the data"""
    write_api = client.write_api(write_options=SYNCHRONOUS)
    delete_api = client.delete_api()

    print(f"Found {len(incorrect_data)} readings to fix")

    if not incorrect_data:
        print("No data to fix!")
        return

    # Ask for confirmation
    first_reading = incorrect_data[0]["original_timestamp"]
    last_reading = incorrect_data[-1]["original_timestamp"]

    print(f"\nData range to fix:")
    print(f"  First reading: {first_reading}")
    print(f"  Last reading:  {last_reading}")
    print(f"  Total readings: {len(incorrect_data)}")
    print(f"\nThis will:")
    print(f"  1. Delete existing readings in this range")
    print(f"  2. Rewrite them with corrected timestamps (+4 hours)")

    # Auto-proceed (remove interactive confirmation for automation)
    print("\nProceeding with timestamp correction...")
    response = "y"

    try:
        # Step 1: Delete the incorrect data
        print(f"\n1. Deleting incorrect data from {first_reading} to {last_reading}...")

        delete_api.delete(
            start=first_reading,
            stop=last_reading
            + timedelta(seconds=1),  # Add 1 second to include last reading
            predicate='_measurement="weather" AND location="weatherbox"',
            bucket=INFLUX_BUCKET,
            org=INFLUX_ORG,
        )

        print("   ✓ Deleted incorrect data")

        # Step 2: Write corrected data
        print(f"2. Writing {len(incorrect_data)} readings with corrected timestamps...")

        points = []
        corrected_count = 0

        for reading in incorrect_data:
            original_time = reading["original_timestamp"]
            # Add 4 hours to correct the timezone issue
            corrected_time = original_time + timedelta(hours=4)

            # Create a point with corrected timestamp
            point = Point("weather").tag("location", "weatherbox")

            # Add all fields
            for field_name, field_value in reading["fields"].items():
                point.field(field_name, field_value)

            # Set the corrected timestamp
            point.time(corrected_time, WritePrecision.S)
            points.append(point)
            corrected_count += 1

            # Write in batches of 1000
            if len(points) >= 1000:
                write_api.write(bucket=INFLUX_BUCKET, record=points)
                points = []
                print(f"   ✓ Written {corrected_count} readings...")

        # Write remaining points
        if points:
            write_api.write(bucket=INFLUX_BUCKET, record=points)

        print(f"   ✓ Successfully corrected {corrected_count} readings")
        print(f"\nTimestamp correction complete!")

        # Show a sample of what was changed
        if incorrect_data:
            sample = incorrect_data[0]
            original = sample["original_timestamp"]
            corrected = original + timedelta(hours=4)
            print(f"\nExample correction:")
            print(f"  Original:  {original}")
            print(f"  Corrected: {corrected}")

    except Exception as e:
        print(f"Error during correction: {e}")
        raise


def main():
    """Main function to fix historical timestamps"""
    print("Historical Timestamp Fix for Weather Station")
    print("=" * 50)

    client = get_influx_client()

    try:
        # Get data that needs fixing
        print("1. Scanning for incorrect timestamps...")
        incorrect_data = get_incorrect_data(client)

        if incorrect_data:
            fix_timestamps_and_rewrite(client, incorrect_data)
        else:
            print("No incorrect data found!")

    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
