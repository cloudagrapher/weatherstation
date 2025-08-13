#!/usr/bin/env python3
"""
WSGI entry point for the weather dashboard
For production deployment with gunicorn
"""

# IMPORTANT: monkey patch must be first
import eventlet

eventlet.monkey_patch()

import threading
import time
from src.dashboard_masterbox import app, socketio, dashboard


def update_data_periodically():
    """Periodically update current data and broadcast to clients"""
    while True:
        try:
            dashboard._update_current_data()
            current_reading = dashboard.get_current_reading()

            if current_reading:
                dashboard.broadcast_update(current_reading, "new_reading")
                print("✓ Data updated and broadcasted")
            else:
                print("✗ No current data available")

        except Exception as e:
            print(f"Error in periodic update: {e}")

        # Wait 30 seconds before next update
        time.sleep(30)


# Set up the SocketIO instance for the dashboard
dashboard.set_socketio(socketio)

# Start periodic data update thread
update_thread = threading.Thread(target=update_data_periodically, daemon=True)
update_thread.start()

print("Weather Dashboard WSGI initialized")
print("Periodic data updates started")

# This is what gunicorn will use
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
else:
    # For gunicorn
    application = app
