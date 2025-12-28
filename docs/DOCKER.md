# Docker Deployment Guide - Retro UI

## Overview

The retro UI can be deployed using Docker alongside the action server and PostgreSQL database.

## Quick Start

### Start All Services

```bash
cd /path/to/linkedin-easy-apply
docker-compose up -d
```

This will start:
- **PostgreSQL** (port 5432) - Database
- **Action Server** (port 8080) - LinkedIn automation
- **Retro UI** (port 3001) - Web interface

### Access the UI

Open your browser to: **http://localhost:3001/index.html**

## Architecture

```
┌─────────────────┐
│   Browser       │
│  (Your PC)      │
└────────┬────────┘
         │ http://localhost:3001
         ▼
┌─────────────────┐
│   Retro UI      │◄────┐
│  (Node.js)      │     │
│   Port 3001     │     │ Reads from DB
└────────┬────────┘     │
         │              │
         │ API Calls    │
         ▼              │
┌─────────────────┐     │
│ Action Server   │     │
│  (Python)       │     │
│   Port 8080     │     │
└────────┬────────┘     │
         │              │
         │ Writes       │
         ▼              │
┌─────────────────┐     │
│   PostgreSQL    │─────┘
│   Port 5432     │
└─────────────────┘
```

## Configuration

### Environment Variables

Edit `docker-compose.yml` to configure:

#### Retro UI Service
```yaml
retro-ui:
  environment:
    # Database type: 'postgres' or 'sqlite'
    - DATABASE_TYPE=postgres
    
    # PostgreSQL connection (if using postgres)
    - DATABASE_URL=postgresql://linkedin_user:dev_password@postgres:5432/linkedin_jobs
    
    # SQLite path (if using sqlite)
    - DB_PATH=/data/linkedin_jobs.sqlite
    
    # Action server URL (container name)
    - ACTION_SERVER_URL=http://action-server:8080
```

### Using SQLite Instead of PostgreSQL

To use SQLite in Docker:

1. Update `docker-compose.yml`:
```yaml
retro-ui:
  environment:
    - DATABASE_TYPE=sqlite
    - DB_PATH=/data/linkedin_jobs.sqlite
  volumes:
    # Mount local SQLite database
    - ./src/linkedin_jobs.sqlite:/data/linkedin_jobs.sqlite:ro
```

2. Comment out PostgreSQL service and remove from `depends_on`

### Port Configuration

Change ports if needed:

```yaml
retro-ui:
  ports:
    - "3002:3001"  # External:Internal
```

Then access at: http://localhost:3002

## Build & Deploy

### Build Images

```bash
# Build all services
docker-compose build

# Build only retro-ui
docker-compose build retro-ui
```

### Start Services

```bash
# Start in background
docker-compose up -d

# Start with logs
docker-compose up

# Start specific service
docker-compose up -d retro-ui
```

### Stop Services

```bash
# Stop all
docker-compose down

# Stop and remove volumes
docker-compose down -v
```

## Monitoring

### View Logs

```bash
# All services
docker-compose logs -f

# Retro UI only
docker-compose logs -f retro-ui

# Last 100 lines
docker-compose logs --tail=100 retro-ui
```

### Check Health

```bash
# Container status
docker-compose ps

# Health check
curl http://localhost:3001/api/health

# Database stats
curl http://localhost:3001/api/stats
```

### Access Container Shell

```bash
# Retro UI container
docker-compose exec retro-ui sh

# Action server container
docker-compose exec action-server bash
```

## Troubleshooting

### Retro UI Won't Start

**Check logs:**
```bash
docker-compose logs retro-ui
```

**Common issues:**

1. **Database connection failed**
   - Verify PostgreSQL is running: `docker-compose ps postgres`
   - Check DATABASE_URL is correct
   - Ensure postgres service is healthy

2. **Port already in use**
   ```bash
   # Find what's using port 3001
   lsof -i :3001
   
   # Change port in docker-compose.yml
   ports:
     - "3002:3001"
   ```

3. **Can't connect to action server**
   - Verify action server is running: `docker-compose ps action-server`
   - Check ACTION_SERVER_URL points to container name, not localhost

### Database Issues

**PostgreSQL not ready:**
```bash
# Wait for health check
docker-compose logs postgres

# Manual check
docker-compose exec postgres psql -U linkedin_user -d linkedin_jobs -c "SELECT 1;"
```

**SQLite file not found:**
```bash
# Check volume mount
docker-compose exec retro-ui ls -la /data/

# Verify file exists locally
ls -la ./src/linkedin_jobs.sqlite
```

### Network Issues

**Containers can't communicate:**
```bash
# Check network
docker network inspect linkedin-easy-apply_linkedin-network

# Test connectivity
docker-compose exec retro-ui ping action-server
```

## Production Deployment

### Security Hardening

1. **Change default passwords** in docker-compose.yml:
```yaml
postgres:
  environment:
    POSTGRES_PASSWORD: <strong-password-here>
```

2. **Use secrets** instead of environment variables:
```yaml
services:
  postgres:
    secrets:
      - postgres_password

secrets:
  postgres_password:
    file: ./secrets/postgres_password.txt
```

3. **Disable debug logging:**
```yaml
retro-ui:
  environment:
    - NODE_ENV=production
```

4. **Use reverse proxy** (nginx/traefik) for SSL:
```yaml
nginx:
  image: nginx:alpine
  ports:
    - "443:443"
  volumes:
    - ./nginx.conf:/etc/nginx/nginx.conf
    - ./ssl:/etc/nginx/ssl
```

### Backup & Restore

**Backup PostgreSQL:**
```bash
docker-compose exec postgres pg_dump -U linkedin_user linkedin_jobs > backup.sql
```

**Restore:**
```bash
cat backup.sql | docker-compose exec -T postgres psql -U linkedin_user -d linkedin_jobs
```

### Scaling

**Multiple retro UI instances:**
```bash
docker-compose up -d --scale retro-ui=3
```

Add load balancer (nginx) to distribute traffic.

## Performance Optimization

### Enable Caching

Add Redis for caching database queries:

```yaml
redis:
  image: redis:alpine
  ports:
    - "6379:6379"
```

### Resource Limits

```yaml
retro-ui:
  deploy:
    resources:
      limits:
        cpus: '0.5'
        memory: 512M
      reservations:
        cpus: '0.25'
        memory: 256M
```

## Development Mode

Mount source for live reload:

```yaml
retro-ui:
  volumes:
    - ./retro-ui:/app
    - /app/node_modules
  environment:
    - NODE_ENV=development
  command: npm run dev
```

## Useful Commands

```bash
# Rebuild and restart
docker-compose up -d --build

# View resource usage
docker stats

# Clean up everything
docker-compose down -v --rmi all

# Export logs
docker-compose logs > logs.txt

# Update single service
docker-compose up -d --no-deps --build retro-ui
```

## Additional Resources

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [PostgreSQL Docker Image](https://hub.docker.com/_/postgres)
- [Node.js Docker Best Practices](https://github.com/nodejs/docker-node/blob/main/docs/BestPractices.md)
