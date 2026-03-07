import os

BACKEND_URL = os.getenv('BACKEND_URL', 'http://backend:8000')
LISTEN_HOST = os.getenv('SOCKS5_LISTEN_HOST', '0.0.0.0')
LISTEN_PORT = int(os.getenv('SOCKS5_LISTEN_PORT', '1080'))
HTTP_TIMEOUT = float(os.getenv('BACKEND_HTTP_TIMEOUT', '15'))
TRAFFIC_FLUSH_BYTES = int(os.getenv('TRAFFIC_FLUSH_BYTES', '1048576'))
