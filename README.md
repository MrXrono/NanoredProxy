# NanoredProxy

NanoredProxy is a containerized SOCKS5 proxy pool manager with:
- FastAPI backend
- custom SOCKS5 gateway
- PostgreSQL + Redis
- React admin UI
- workers for availability, geo, speedtest, aggregates, reconciliation

## Features
- import upstream SOCKS5 proxies with or without auth
- dynamic country accounts (`all:all`, `de:de`, `ru:ru`, ...)
- composite score, sticky sessions, A/B routing
- speedtest scheduling with pause/resume rules
- quarantine windows and stability scoring
- full traffic accounting per session/connection/account/proxy
- unified proxychains config generation
- admin UI session kill
- websocket realtime events for admin UI
- alembic bootstrap migration

## Quick start
```bash
cp .env.example .env
docker compose up --build
```

## Services
- Backend: `http://localhost:8000/docs`
- Frontend: `http://localhost:3000`
- SOCKS5 Gateway: `localhost:1080`
- Realtime WS: `ws://localhost:8000/api/v1/ws/events?token=<JWT>`

## Migrations
```bash
cd backend
alembic upgrade head
```

## Notes
Current repository contains implemented backend API, gateway base routing, workers, realtime admin events, and integration/unit tests.

## Tests
```bash
cd backend && pytest -q
cd ../frontend && npm run build
```
