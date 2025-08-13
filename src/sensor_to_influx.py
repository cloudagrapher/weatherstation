#!/home/weatherbox/weatherstation/.venv/bin/python
"""
Simplified Weather Station - Sensors to InfluxDB
High-frequency readings from DHT22 + MPL115A2 sent to InfluxDB on masterbox
"""

import time
import struct
from datetime import datetime
import Adafruit_DHT
import RPi.GPIO as GPIO
import smbus2
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# Sensor Configuration
DHT_SENSOR = Adafruit_DHT.DHT22
DHT_PIN = 4

# MPL115A2 Configuration
MPL115A2_ADDRESS = 0x60
RST_PIN = 17  # GPIO 17 (Pin 11)
SDWN_PIN = 27  # GPIO 27 (Pin 13)

# Try to import configuration, fall back to defaults
try:
    from ..config.influxdb_config import (
        INFLUX_HOST,
        INFLUX_PORT,
        INFLUX_ORG,
        INFLUX_BUCKET,
        INFLUX_TOKEN,
    )
except ImportError:
    # Default configuration - update influxdb_config.py with your actual values
    INFLUX_HOST = "masterbox"  # or use IP address like "192.168.1.100"
    INFLUX_PORT = 8086
    INFLUX_ORG = "home"
    INFLUX_BUCKET = "sensors"
    INFLUX_TOKEN = "your-influxdb-token-here"  # Update this with your actual token

# Reading interval (sensors can handle ~1 reading per second)
READING_INTERVAL = 2.0  # seconds between readings


class MPL115A2:
    def __init__(self):
        self.bus = None
        self.address = MPL115A2_ADDRESS
        self.initialized = False
        self.coefficients_read = False
        self._initialize_gpio()
        self._initialize_sensor()

    def _initialize_gpio(self):
        """Initialize GPIO pins for sensor control"""
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            GPIO.setup(RST_PIN, GPIO.OUT)
            GPIO.setup(SDWN_PIN, GPIO.OUT)

            # Enable the sensor (both pins high)
            GPIO.output(SDWN_PIN, GPIO.HIGH)  # Take out of shutdown
            GPIO.output(RST_PIN, GPIO.HIGH)  # Take out of reset

            time.sleep(0.1)  # Give it time to initialize
            print("MPL115A2 GPIO initialized")
        except Exception as e:
            print(f"GPIO initialization error: {e}")

    def _initialize_sensor(self):
        """Initialize I2C communication and read coefficients"""
        try:
            self.bus = smbus2.SMBus(1)
            self._read_coefficients()
            self.initialized = True
            print("MPL115A2 sensor initialized successfully")
        except Exception as e:
            print(f"MPL115A2 initialization error: {e}")
            self.initialized = False

    def _read_coefficients(self):
        """Read calibration coefficients"""
        try:
            # Read coefficients from registers 0x04-0x0B
            data = self.bus.read_i2c_block_data(self.address, 0x04, 8)

            # Convert to signed integers and apply scaling
            self.a0 = struct.unpack(">h", bytes(data[0:2]))[0] / 8.0
            self.b1 = struct.unpack(">h", bytes(data[2:4]))[0] / 8192.0
            self.b2 = struct.unpack(">h", bytes(data[4:6]))[0] / 16384.0
            self.c12 = struct.unpack(">h", bytes(data[6:8]))[0] / 4194304.0

            self.coefficients_read = True
            print(
                f"Coefficients: a0={self.a0:.2f}, b1={self.b1:.6f}, "
                f"b2={self.b2:.6f}, c12={self.c12:.9f}"
            )

        except Exception as e:
            print(f"Coefficient read error: {e}")
            # Use default values if reading fails
            self.a0 = 2009.75
            self.b1 = -2.37585
            self.b2 = -0.92047
            self.c12 = 0.000790
            self.coefficients_read = False

    def read_pressure(self):
        """Read pressure in hPa"""
        if not self.initialized:
            return None

        try:
            # Start conversion by writing to register 0x12
            self.bus.write_byte_data(self.address, 0x12, 0x01)
            time.sleep(0.005)  # Wait for conversion (3ms minimum)

            # Read pressure and temperature data from registers 0x00-0x03
            data = self.bus.read_i2c_block_data(self.address, 0x00, 4)

            # Convert raw data (10-bit values, left-justified in 16-bit registers)
            pressure_raw = ((data[0] << 8) | data[1]) >> 6
            temp_raw = ((data[2] << 8) | data[3]) >> 6

            # Calculate compensated pressure using calibration coefficients
            pressure_comp = (
                self.a0
                + (self.b1 + self.c12 * temp_raw) * pressure_raw
                + self.b2 * temp_raw
            )

            # Convert to kPa then to hPa (hectopascals/millibars)
            pressure_kpa = pressure_comp * (115.0 - 50.0) / 1023.0 + 50.0
            pressure_hpa = pressure_kpa * 10.0  # Convert kPa to hPa

            # Apply calibration offset
            calibration_offset = -300.0  # Subtract 300 hPa
            pressure_calibrated = pressure_hpa + calibration_offset

            return round(pressure_calibrated, 2)

        except Exception as e:
            print(f"Pressure read error: {e}")
            return None

    def cleanup(self):
        """Clean up GPIO resources"""
        try:
            if self.bus:
                self.bus.close()
            GPIO.cleanup()
        except:
            pass


class SensorLogger:
    def __init__(self):
        self.pressure_sensor = MPL115A2()
        self.influx_client = None
        self.write_api = None
        self._setup_influxdb()

    def _setup_influxdb(self):
        """Initialize InfluxDB connection"""
        try:
            self.influx_client = InfluxDBClient(
                url=f"http://{INFLUX_HOST}:{INFLUX_PORT}",
                token=INFLUX_TOKEN,
                org=INFLUX_ORG,
            )
            self.write_api = self.influx_client.write_api(write_options=SYNCHRONOUS)
            print(f"Connected to InfluxDB at {INFLUX_HOST}:{INFLUX_PORT}")
        except Exception as e:
            print(f"InfluxDB connection error: {e}")
            print("Continuing without InfluxDB - readings will be printed only")

    def read_sensors(self):
        """Read all sensors and return data"""
        data = {}

        # Read DHT22 with retries
        humidity, temperature_c = Adafruit_DHT.read_retry(
            DHT_SENSOR, DHT_PIN, retries=3, delay_seconds=1
        )

        if humidity is not None and temperature_c is not None:
            # Validate readings are reasonable
            if -40 <= temperature_c <= 80 and 0 <= humidity <= 100:
                temp_f = temperature_c * 9.0 / 5.0 + 32.0
                data.update(
                    {
                        "temperature_c": round(temperature_c, 2),
                        "temperature_f": round(temp_f, 2),
                        "humidity": round(humidity, 2),
                    }
                )

        # Read MPL115A2
        pressure_hpa = self.pressure_sensor.read_pressure()
        if pressure_hpa is not None:
            data["pressure_hpa"] = pressure_hpa

        data["timestamp"] = datetime.now()
        return (
            data if len(data) > 1 else None
        )  # Must have at least timestamp + one reading

    def send_to_influxdb(self, data):
        """Send data to InfluxDB"""
        if not self.write_api:
            return False

        try:
            point = (
                Point("weather")
                .tag("location", "weatherbox")
                .tag("sensor_type", "dht22_mpl115a2")
            )

            # Add fields
            if "temperature_c" in data:
                point.field("temperature_c", data["temperature_c"])
            if "temperature_f" in data:
                point.field("temperature_f", data["temperature_f"])
            if "humidity" in data:
                point.field("humidity", data["humidity"])
            if "pressure_hpa" in data:
                point.field("pressure_hpa", data["pressure_hpa"])

            point.time(data["timestamp"], WritePrecision.S)

            self.write_api.write(bucket=INFLUX_BUCKET, record=point)
            return True

        except Exception as e:
            print(f"InfluxDB write error: {e}")
            return False

    def log_reading(self, data):
        """Print reading in a readable format"""
        timestamp = data["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
        temp_str = f"{data.get('temperature_f', 'N/A')}°F ({data.get('temperature_c', 'N/A')}°C)"
        humidity_str = f"{data.get('humidity', 'N/A')}%"
        pressure_str = f"{data.get('pressure_hpa', 'N/A')} hPa"

        print(
            f"[{timestamp}] Temp: {temp_str}, Humidity: {humidity_str}, Pressure: {pressure_str}"
        )

    def run(self):
        """Main sensor reading loop"""
        print("Starting high-frequency sensor logging...")
        print(f"Reading interval: {READING_INTERVAL} seconds")
        print(f"Target: InfluxDB at {INFLUX_HOST}:{INFLUX_PORT}")
        print("Press Ctrl+C to stop\n")

        try:
            while True:
                data = self.read_sensors()

                if data:
                    # Log to console
                    self.log_reading(data)

                    # Send to InfluxDB
                    if self.send_to_influxdb(data):
                        print("  → Sent to InfluxDB ✓")
                    else:
                        print("  → InfluxDB failed ✗")
                else:
                    print(
                        f"[{datetime.now().strftime('%H:%M:%S')}] No valid sensor data"
                    )

                time.sleep(READING_INTERVAL)

        except KeyboardInterrupt:
            print("\nShutting down sensor logger...")
        except Exception as e:
            print(f"Unexpected error: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources"""
        print("Cleaning up...")
        self.pressure_sensor.cleanup()
        if self.influx_client:
            self.influx_client.close()
        print("Cleanup complete")


def main():
    logger = SensorLogger()
    logger.run()


if __name__ == "__main__":
    main()
