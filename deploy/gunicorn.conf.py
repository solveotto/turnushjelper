# Gunicorn configuration — Hetzner production
#
# Used by the systemd service (/etc/systemd/system/turnushjelper.service):
#   ExecStart=.../gunicorn --workers 2 --bind unix:/run/turnushjelper/turnushjelper.sock ...
#
# To scale up on a larger server (each worker uses ~150-200 MB RAM):
#   workers = 4
#   threads = 4    # effective concurrency = workers × threads

# --- Workers ---
workers = 2
worker_class = "gthread"
threads = 4          # effective concurrency = workers × threads (here: 8)

# --- Binding ---
bind = "unix:/run/turnushjelper/turnushjelper.sock"

# --- Timeouts ---
timeout = 300        # allow long PDF/Excel generation requests
keepalive = 5
graceful_timeout = 10

# --- Logging ---
accesslog = "/var/log/turnushjelper/access.log"
errorlog = "/var/log/turnushjelper/error.log"
loglevel = "warning"

# --- Process ---
proc_name = "turnushjelper"
