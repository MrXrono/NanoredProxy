import os
BACKEND_URL = os.getenv('BACKEND_URL', 'http://backend:8000')
LISTEN_HOST = os.getenv('SOCKS5_LISTEN_HOST', '0.0.0.0')
LISTEN_PORT = int(os.getenv('SOCKS5_LISTEN_PORT', '1080'))
