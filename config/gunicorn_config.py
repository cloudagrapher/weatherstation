# Gunicorn configuration for Weather Dashboard
import os

# Server socket
bind = "0.0.0.0:5000"
backlog = 2048

# Worker processes
workers = 1  # Use only 1 worker for Flask-SocketIO compatibility
worker_class = "eventlet"  # Required for WebSocket support
worker_connections = 1000
timeout = 30
keepalive = 2

# Restart workers after this many requests, to prevent memory leaks
max_requests = 1000
max_requests_jitter = 50

# Logging
errorlog = "-"  # Log to stderr (handled by systemd)
accesslog = "-"  # Log to stdout (handled by systemd)
loglevel = "info"

# Process naming
proc_name = "weather-dashboard"

# User/group to run as (will be set in systemd service)
# user = "masterbox"
# group = "masterbox"

# Preload app
preload_app = True

# Graceful timeout
graceful_timeout = 30

# Environment variables
os.environ.setdefault("FLASK_ENV", "production")
