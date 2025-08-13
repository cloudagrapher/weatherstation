#!/usr/bin/env python3
"""
Script to check existing weather events in InfluxDB
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from influxdb_data_service import WeatherDataService

def main():
    service = WeatherDataService()
    events = service.get_recent_weather_events(50)  # Get last 50 events
    
    print(f"Found {len(events)} weather events:")
    print("-" * 80)
    
    for i, event in enumerate(events):
        print(f"{i+1:2d}. {event['timestamp']} - {event['event_type']}")
        if event.get('intensity'):
            print(f"    Intensity: {event['intensity']}")
        if event.get('notes'):
            print(f"    Notes: {event['notes']}")
        print()

if __name__ == "__main__":
    main()