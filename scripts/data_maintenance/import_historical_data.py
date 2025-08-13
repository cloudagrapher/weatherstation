#!/usr/bin/env python3
"""
Import Historical Weather Data to InfluxDB
Reads weather_data.json and imports all historical readings to InfluxDB
"""

import json
import sys
from datetime import datetime
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# Try to import configuration
try:
    from influxdb_config import (
        INFLUX_HOST,
        INFLUX_PORT,
        INFLUX_ORG,
        INFLUX_BUCKET,
        INFLUX_TOKEN,
    )
except ImportError:
    print("Error: influxdb_config.py not found or incomplete")
    print("Please ensure influxdb_config.py exists with proper configuration")
    sys.exit(1)

DATA_FILE = "weather_data.json"


def load_historical_data():
    """Load historical data from JSON file"""
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
        print(f"Loaded {len(data)} historical readings from {DATA_FILE}")
        return data
    except FileNotFoundError:
        print(f"Error: {DATA_FILE} not found")
        return None
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        return None


def create_influxdb_point(reading):
    """Convert a weather reading to an InfluxDB point"""
    try:
        # Parse timestamp
        timestamp = datetime.fromisoformat(reading["timestamp"])

        # Create point
        point = (
            Point("weather")
            .tag("location", "weatherbox")
            .tag("sensor_type", "dht22_mpl115a2")
            .tag("import", "historical")
        )

        # Add temperature fields
        if "temperature_c" in reading:
            point.field("temperature_c", float(reading["temperature_c"]))
        if "temperature_f" in reading:
            point.field("temperature_f", float(reading["temperature_f"]))

        # Add humidity field
        if "humidity" in reading:
            point.field("humidity", float(reading["humidity"]))

        # Add pressure field if available
        if "pressure_hpa" in reading and reading["pressure_hpa"] is not None:
            point.field("pressure_hpa", float(reading["pressure_hpa"]))

        point.time(timestamp, WritePrecision.S)
        return point

    except Exception as e:
        print(
            f"Error creating point for reading {reading.get('timestamp', 'unknown')}: {e}"
        )
        return None


def import_data_to_influxdb(historical_data):
    """Import historical data to InfluxDB"""
    try:
        # Connect to InfluxDB
        client = InfluxDBClient(
            url=f"http://{INFLUX_HOST}:{INFLUX_PORT}",
            token=INFLUX_TOKEN,
            org=INFLUX_ORG,
        )
        write_api = client.write_api(write_options=SYNCHRONOUS)

        print(f"Connected to InfluxDB at {INFLUX_HOST}:{INFLUX_PORT}")
        print(f"Importing to bucket: {INFLUX_BUCKET}")

        # Convert readings to points
        points = []
        skipped = 0

        for reading in historical_data:
            point = create_influxdb_point(reading)
            if point:
                points.append(point)
            else:
                skipped += 1

        print(f"Created {len(points)} points ({skipped} skipped)")

        if not points:
            print("No valid points to import")
            return False

        # Write in batches for better performance
        batch_size = 1000
        total_batches = (len(points) + batch_size - 1) // batch_size

        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            batch_num = (i // batch_size) + 1

            try:
                write_api.write(bucket=INFLUX_BUCKET, record=batch)
                print(
                    f"  Batch {batch_num}/{total_batches}: {len(batch)} points written"
                )
            except Exception as e:
                print(f"  Batch {batch_num}/{total_batches}: Error writing batch: {e}")
                return False

        print(f"✓ Successfully imported {len(points)} historical readings to InfluxDB")
        client.close()
        return True

    except Exception as e:
        print(f"Error connecting to InfluxDB: {e}")
        return False


def main():
    """Main import function"""
    print("Historical Weather Data Import Tool")
    print("===================================")

    # Load historical data
    historical_data = load_historical_data()
    if not historical_data:
        return

    # Show data range
    if historical_data:
        first_reading = historical_data[0]["timestamp"]
        last_reading = historical_data[-1]["timestamp"]
        print(f"Data range: {first_reading} to {last_reading}")

    # Confirm import
    response = input(f"\nImport {len(historical_data)} readings to InfluxDB? (y/N): ")
    if response.lower() != "y":
        print("Import cancelled")
        return

    # Import data
    success = import_data_to_influxdb(historical_data)

    if success:
        print("\n✓ Historical data import completed successfully!")
        print("You can now query the data in InfluxDB using the 'weather' measurement")
    else:
        print("\n✗ Import failed. Check the error messages above.")


if __name__ == "__main__":
    main()
