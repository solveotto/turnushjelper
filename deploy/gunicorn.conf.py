# Gunicorn configuration — production-tuned for PythonAnywhere
#
# Usage: reference this file in the PythonAnywhere web config WSGI command:
#   gunicorn --config deploy/gunicorn.conf.py wsgi:app
#
# PythonAnywhere plan guide:
#   Hacker  (~$5/mo)  — 2 workers is safe, threads=2 gives effective concurrency of 4
#   Web Dev (~$12/mo) — raise workers to 4 for ~8 effective concurrent requests

# --- Workers ---
workers = 2          # increase to 4 on Web Developer plan or higher
worker_class = "gthread"  # I/O-concurrent threading; each worker handles `threads` requests at once
threads = 2          # effective concurrency = workers × threads (here: 4)

# --- Timeouts ---
timeout = 30         # kill a worker that takes longer than 30 s (prevents hung PDF/Excel requests blocking slots)
keepalive = 5        # hold idle HTTP connections open for 5 s (reduces reconnect overhead)
graceful_timeout = 10  # time to finish in-flight requests before a forced restart

# --- Logging ---
accesslog = "-"      # stdout (captured by PythonAnywhere)
errorlog = "-"       # stderr
loglevel = "warning" # reduce noise; set to "info" temporarily when debugging traffic spikes

# --- Process ---
proc_name = "shift_rotation_organizer"
