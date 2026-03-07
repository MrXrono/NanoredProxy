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

## Quick start
```bash
cp .env.example .env
docker compose up --build
```

## Services
- Backend: `http://localhost:8000/docs`
- Frontend: `http://localhost:3000`
- SOCKS5 Gateway: `localhost:1080`

## Notes
This repository contains a production-oriented scaffold with core API, models, workers, and gateway skeleton. Business logic extension points are marked in code.


## Current state

Implemented in repository now:
- JWT-protected admin API
- React admin UI with login, dashboard, proxies, accounts, sessions, workers, config and audit pages
- Basic unit tests for parser/security/config/scoring

Run tests:
```bash
cd backend && pytest -q
cd ../workers && PYTHONPATH=/workspace/NanoredProxy pytest -q
```
