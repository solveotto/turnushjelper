# Gunicorn config — used for VPS or manual deployment.
# PythonAnywhere's standard WSGI hosting does NOT use this file.
# To use: gunicorn -c gunicorn.conf.py run:app

workers = 2           # conservative for PythonAnywhere; tune up on a VPS with more RAM
worker_class = "gthread"
threads = 4           # 2 workers × 4 threads = 8 concurrent requests
timeout = 60
keepalive = 5
bind = "0.0.0.0:8080"
accesslog = "-"       # stdout
errorlog = "-"        # stderr
