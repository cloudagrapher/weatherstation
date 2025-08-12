#!/usr/bin/env python3
"""
Test script to verify feels like calculations work correctly
"""

import sys
import os
import math
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dashboard_masterbox import WeatherDashboard

def test_feels_like():
    dashboard = WeatherDashboard()
    
    test_cases = [
        # (temp_f, humidity, expected_condition, description)
        (85, 80, "heat_index", "Hot and humid - should use heat index"),
        (45, 60, "apparent_temp", "Cool weather - should use apparent temperature"),
        (30, 50, "wind_chill", "Cold weather - should use wind chill (no wind)"),
        (75, 50, "apparent_temp", "Comfortable conditions"),
        (95, 70, "heat_index", "Very hot and humid"),
        (100, 20, "apparent_temp", "Hot but dry - heat index doesn't apply"),
    ]
    
    print("Testing Feels Like Calculations")
    print("=" * 60)
    
    for temp_f, humidity, expected_condition, description in test_cases:
        feels_like = dashboard.calculate_feels_like(temp_f, humidity)
        comfort_desc = dashboard.get_comfort_description(feels_like, humidity)
        
        print(f"\\n{description}")
        print(f"Actual: {temp_f}°F, {humidity}% humidity")
        print(f"Feels like: {feels_like}°F")
        print(f"Difference: {feels_like - temp_f:+.1f}°F")
        print(f"Comfort: {', '.join(comfort_desc)}")
        
        # Test individual methods for verification
        if temp_f >= 80 and humidity >= 40:
            heat_index = dashboard.heat_index(temp_f, humidity)
            print(f"Heat Index method: {heat_index}°F")
        elif temp_f <= 50:
            wind_chill = dashboard.wind_chill(temp_f, 0)  # no wind
            print(f"Wind Chill method: {wind_chill}°F")
        else:
            temp_c = (temp_f - 32) * 5/9
            apparent = dashboard.apparent_temperature(temp_c, humidity, 0)
            print(f"Apparent Temp method: {apparent}°F")

if __name__ == "__main__":
    test_feels_like()