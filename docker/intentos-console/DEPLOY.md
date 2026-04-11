# IntentOS Console — Docker Deployment

## Prerequisites

- Docker Engine 24+ ([Install Docker](https://docs.docker.com/engine/install/))
- Docker Compose v2+ (included with Docker Desktop)

## Quick Start

```bash
cd docker/intentos-console
cp .env.example .env
# Edit .env with your secrets
docker compose up -d
```

The console will be available at:
- Frontend: http://localhost:3000
- API: http://localhost:8000

## Production Checklist

- [ ] Change `POSTGRES_PASSWORD` to a strong random value
- [ ] Change `SECRET_KEY` to a cryptographically random string (min 32 chars)
- [ ] Set `CORS_ORIGINS` to your actual domain
- [ ] Set up SSL/TLS termination (nginx reverse proxy or cloud load balancer)
- [ ] Configure PostgreSQL backups (pg_dump cron or managed service)
- [ ] Set up Redis persistence if session durability is needed
- [ ] Configure log aggregation (stdout logs are Docker-native)
- [ ] Set resource limits in docker-compose.yml for production workloads

## Services

| Service    | Port | Description                          |
|------------|------|--------------------------------------|
| `frontend` | 3000 | Nginx serving the console SPA        |
| `console`  | 8000 | FastAPI backend (Python)             |
| `postgres` | 5432 | PostgreSQL 16 database               |
| `redis`    | 6379 | Redis 7 for sessions and caching     |

## Commands

```bash
# View logs
docker compose logs -f console

# Restart a service
docker compose restart console

# Stop everything
docker compose down

# Stop and remove volumes (destroys data)
docker compose down -v

# Rebuild after code changes
docker compose build --no-cache
docker compose up -d
```
