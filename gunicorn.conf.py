# Gunicorn config for Hetzner production deployment.
# The systemd service references this via: gunicorn -c gunicorn.conf.py "app:create_app()"
# To use manually: gunicorn -c gunicorn.conf.py "app:create_app()"

workers = 2           # tune up if server has more RAM (each worker ~150-200 MB)
worker_class = "gthread"
threads = 4           # 2 workers × 4 threads = 8 concurrent requests
timeout = 60
keepalive = 5
bind = "0.0.0.0:8080"
accesslog = "-"       # stdout
errorlog = "-"        # stderr
