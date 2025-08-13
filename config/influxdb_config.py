"""
InfluxDB Configuration for Weather Station
Copy this file and update the values for your setup
"""

# InfluxDB Configuration (masterbox)
INFLUX_HOST = "localhost"  # Change to your masterbox IP if different
INFLUX_PORT = 8086
INFLUX_ORG = "weatherbox"
INFLUX_BUCKET = "sensors"

# You need to generate this token in your InfluxDB admin interface
# Go to http://masterbox:8086 -> Data -> Tokens -> Generate Token
INFLUX_TOKEN = "eIgZcGG5oncaSFOIjftY-8PfzZLwd4ign7TTPq3611gO5Yv_fccW3b4WL3-zOFT7gkj9BGzYO5yVs178VzN0Eg=="

# Optional: Database name for legacy InfluxDB 1.x compatibility
# INFLUX_DATABASE = "weatherstation"
