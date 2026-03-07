# Deployment

Files for production-style deployment:
- `nginx/nginx.conf` reverse proxy for frontend/backend websocket
- `nginx/default.conf` server config
- `systemd/nanoredproxy.service.example` sample service wrapper for docker compose
- `docker-compose.prod.yml` production compose profile
