import os

bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
workers = int(os.getenv('GUNICORN_WORKERS', '4'))
worker_class = os.getenv('GUNICORN_WORKER_CLASS', 'sync')
timeout = int(os.getenv('GUNICORN_TIMEOUT', '120'))
graceful_timeout = int(os.getenv('GUNICORN_GRACEFUL_TIMEOUT', '30'))
accesslog = '-'
errorlog = '-'
capture_output = True
