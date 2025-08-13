#!/usr/bin/env python3
"""
Test script to verify feels like summary calculations
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from influxdb_data_service import WeatherDataService

def test_feels_like_summary():
    service = WeatherDataService()
    summary = service.get_daily_summary()
    
    if not summary:
        print("No daily summary data available")
        return
    
    print("Daily Summary with Feels Like Data")
    print("=" * 50)
    
    # Temperature data
    if 'temp_high' in summary and 'temp_low' in summary:
        print(f"Actual Temperature:")
        print(f"  High: {summary['temp_high']}°F")
        print(f"  Low:  {summary['temp_low']}°F")
        print(f"  Range: {summary['temp_high'] - summary['temp_low']:.1f}°F")
    
    # Feels like data
    if 'feels_like_high' in summary and 'feels_like_low' in summary:
        print(f"\\nFeels Like Temperature:")
        print(f"  High: {summary['feels_like_high']}°F")
        print(f"  Low:  {summary['feels_like_low']}°F")
        print(f"  Range: {summary['feels_like_high'] - summary['feels_like_low']:.1f}°F")
        
        # Calculate differences
        if 'temp_high' in summary and 'temp_low' in summary:
            high_diff = summary['feels_like_high'] - summary['temp_high']
            low_diff = summary['feels_like_low'] - summary['temp_low']
            print(f"\\nDifferences (Feels Like - Actual):")
            print(f"  High: {high_diff:+.1f}°F")
            print(f"  Low:  {low_diff:+.1f}°F")
    
    # Humidity context
    if 'humidity_high' in summary and 'humidity_low' in summary:
        print(f"\\nHumidity Context:")
        print(f"  High: {summary['humidity_high']}%")
        print(f"  Low:  {summary['humidity_low']}%")
    
    print(f"\\nTotal readings analyzed: {summary.get('readings_count', 'Unknown')}")

if __name__ == "__main__":
    test_feels_like_summary()