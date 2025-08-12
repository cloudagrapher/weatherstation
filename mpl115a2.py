import RPi.GPIO as GPIO
import smbus2
import struct

# MPL115A2 Configuration
MPL115A2_ADDRESS = 0x60
RST_PIN = 17  # GPIO 17 (Pin 11)
SDWN_PIN = 27  # GPIO 27 (Pin 13)

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

    def reset_sensor(self):
        """Reset the sensor if needed"""
        try:
            GPIO.output(RST_PIN, GPIO.LOW)
            time.sleep(0.01)
            GPIO.output(RST_PIN, GPIO.HIGH)
            time.sleep(0.1)
            self._read_coefficients()
            print("MPL115A2 sensor reset")
        except Exception as e:
            print(f"Sensor reset error: {e}")

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
                f"Coefficients: a0={self.a0:.2f}, b1={self.b1:.6f}, b2={self.b2:.6f}, c12={self.c12:.9f}"
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
            # MPL115A2 outputs 50-115 kPa range
            pressure_kpa = pressure_comp * (115.0 - 50.0) / 1023.0 + 50.0
            pressure_hpa = pressure_kpa * 10.0  # Convert kPa to hPa

            # Apply calibration offset (adjust this value based on local weather station)
            # Current local pressure is ~1021 hPa, sensor reads ~1320 hPa
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
