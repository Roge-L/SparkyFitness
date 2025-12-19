# SparkyFitness Fly.io Deployment Guide

A guide explaining how we deployed SparkyFitness to Fly.io, covering Docker, networking, and cloud deployment concepts.

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Docker Basics](#docker-basics)
3. [Fly.io Concepts](#flyio-concepts)
4. [The Deployment Process](#the-deployment-process)
5. [Networking Deep Dive](#networking-deep-dive)
6. [Configuration Files Explained](#configuration-files-explained)

---

## Architecture Overview

SparkyFitness has three components:

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   Frontend  │ ───► │   Backend   │ ───► │  Postgres   │
│   (nginx)   │      │  (Node.js)  │      │  Database   │
└─────────────┘      └─────────────┘      └─────────────┘
     :80                  :3010               :5432
```

- **Frontend**: React app served by nginx (reverse proxy)
- **Backend**: Node.js/Express API server
- **Database**: PostgreSQL for data persistence

---

## Docker Basics

### What is Docker?

Docker packages applications into **containers** - lightweight, standalone units that include everything needed to run: code, runtime, libraries, and settings.

**Key concepts:**
- **Image**: A read-only template (like a snapshot of an app)
- **Container**: A running instance of an image
- **Registry**: A place to store/share images (like DockerHub)

**Docs**: https://docs.docker.com/get-started/

### How SparkyFitness Uses Docker

SparkyFitness publishes pre-built images to DockerHub:
- `codewithcj/sparkyfitness:latest` - Frontend
- `codewithcj/sparkyfitness_server:latest` - Backend

Instead of building from source, Fly.io pulls these images directly:

```toml
[build]
  image = "codewithcj/sparkyfitness_server:latest"
```

This is faster than building and ensures consistency.

**Docs**: https://fly.io/docs/languages-and-frameworks/dockerfile/

---

## Fly.io Concepts

### What is Fly.io?

Fly.io runs your Docker containers on servers worldwide. It's simpler than AWS/GCP but more powerful than Heroku.

**Key concepts:**

| Concept | What it is |
|---------|-----------|
| **App** | A deployed application (has a unique name) |
| **Machine** | A micro-VM running your container |
| **Region** | Physical location (e.g., `iad` = Virginia) |
| **Fly Proxy** | Load balancer that routes traffic to your machines |

**Docs**: https://fly.io/docs/apps/overview/

### Machines and Auto-scaling

Fly.io can automatically start/stop machines based on traffic:

```toml
[http_service]
  auto_stop_machines = 'stop'    # Stop when idle (saves money)
  auto_start_machines = true     # Start when request comes in
  min_machines_running = 0       # Allow all machines to stop
```

For the backend, we disabled auto-stop because internal traffic doesn't trigger auto-start:

```toml
  auto_stop_machines = 'off'
  min_machines_running = 1       # Always keep 1 running
```

**Docs**: https://fly.io/docs/launch/autostop-autostart/

---

## The Deployment Process

### Step 1: Create the Database

```bash
flyctl postgres create --name sparkyfitness-db --region iad
```

This creates a managed Postgres cluster. Fly.io handles backups, failover, etc.

**Docs**: https://fly.io/docs/postgres/

### Step 2: Create the Apps

```bash
flyctl apps create sparkyfitness-server --org personal
flyctl apps create sparkyfitness --org personal
```

### Step 3: Attach Database to Backend

```bash
flyctl postgres attach sparkyfitness-db --app sparkyfitness-server
```

This:
1. Creates a database user
2. Sets `DATABASE_URL` secret on the app
3. Configures network access

### Step 4: Set Secrets

Secrets are encrypted environment variables:

```bash
flyctl secrets set \
  SESSION_SECRET="..." \
  JWT_SECRET="..." \
  --app sparkyfitness-server
```

**Important**: Never put secrets in `fly.toml` - that file is committed to git!

**Docs**: https://fly.io/docs/reference/secrets/

### Step 5: Deploy

```bash
flyctl deploy --ha=false
```

- `--ha=false` creates only 1 machine (default is 2 for high availability)
- Fly.io pulls the Docker image and starts the container

---

## Networking Deep Dive

This was the trickiest part. Understanding Fly.io networking is crucial.

### Three Types of Hostnames

| Hostname | Example | Routes Through | Use Case |
|----------|---------|----------------|----------|
| `.fly.dev` | `sparkyfitness-server.fly.dev` | Public internet | External access |
| `.internal` | `sparkyfitness-server.internal` | Direct to machine | Same-org private traffic |
| `.flycast` | `sparkyfitness-server.flycast` | Fly Proxy (private) | Private load-balanced traffic |

**Docs**: https://fly.io/docs/networking/private-networking/

### Why We Used Flycast

The frontend nginx needs to proxy API requests to the backend:

```
User → Frontend (nginx) → Backend
```

**Problem with `.internal`**:
- Nginx validates DNS at startup
- `.internal` DNS wasn't available during nginx config validation
- nginx failed to start with "host not found in upstream"

**Solution - Flycast**:
- Allocate a private IPv6 address: `flyctl ips allocate-v6 --private`
- Use `.flycast` hostname which resolves immediately
- Traffic still stays private (never leaves Fly.io network)

**Docs**: https://fly.io/docs/networking/flycast/

### The Port 80 vs 3010 Issue

**How Fly Proxy works:**

```
                    ┌─────────────────┐
Internet (:443) ──► │   Fly Proxy     │ ──► Container (:3010)
                    │  (handles TLS)  │
                    └─────────────────┘
```

The Fly Proxy:
1. Listens on ports 80/443
2. Handles TLS termination
3. Forwards to your `internal_port`

**Flycast uses the same proxy**, so it listens on port 80, not your internal port!

```toml
# Wrong - Flycast doesn't expose port 3010
SPARKY_FITNESS_SERVER_PORT = "3010"

# Correct - Flycast routes through Fly Proxy on port 80
SPARKY_FITNESS_SERVER_PORT = "80"
```

### force_https Setting

```toml
force_https = true   # Redirects HTTP → HTTPS
force_https = false  # Allows HTTP
```

We set `force_https = false` on the backend because:
- Internal Flycast traffic uses HTTP (TLS is unnecessary inside the private network)
- With `force_https = true`, the proxy returned 301 redirects that broke internal routing

**Docs**: https://fly.io/docs/networking/services/#force_https

---

## Configuration Files Explained

### fly.toml (Backend)

```toml
app = 'sparkyfitness-server'       # Unique app name
primary_region = 'iad'             # Deploy to Virginia

[build]
  image = "codewithcj/sparkyfitness_server:latest"  # DockerHub image

[env]                              # Non-secret environment variables
  NODE_ENV = "production"
  SPARKY_FITNESS_SERVER_PORT = "3010"
  SPARKY_FITNESS_LOG_LEVEL = "INFO"
  TZ = "Etc/UTC"

[http_service]
  internal_port = 3010             # Port your app listens on
  force_https = false              # Allow HTTP for internal traffic
  auto_stop_machines = 'off'       # Never auto-stop
  auto_start_machines = true
  min_machines_running = 1         # Always keep 1 running
  processes = ['app']

[[http_service.checks]]            # Health check configuration
  grace_period = "10s"             # Wait before first check
  interval = "30s"                 # Check every 30s
  method = "GET"
  timeout = "5s"
  path = "/health"                 # Endpoint to check

[[vm]]                             # Machine size
  memory = '512mb'
  cpu_kind = 'shared'
  cpus = 1
```

**Docs**: https://fly.io/docs/reference/configuration/

### fly.toml (Frontend)

```toml
app = 'sparkyfitness'
primary_region = 'iad'

[build]
  image = "codewithcj/sparkyfitness:latest"

[env]
  # These configure nginx to proxy to the backend
  SPARKY_FITNESS_SERVER_HOST = "sparkyfitness-server.flycast"
  SPARKY_FITNESS_SERVER_PORT = "80"    # Flycast uses port 80!

[http_service]
  internal_port = 80               # nginx listens on 80
  force_https = true               # Redirect users to HTTPS
  auto_stop_machines = 'stop'      # OK to stop when idle
  auto_start_machines = true       # Fly Proxy wakes it up
  min_machines_running = 0

[[http_service.checks]]
  path = "/"                       # Check the homepage

[[vm]]
  memory = '256mb'                 # Frontend needs less memory
  cpu_kind = 'shared'
  cpus = 1
```

---

## Key Takeaways

1. **Docker images are portable** - Build once, run anywhere
2. **Fly.io handles the hard parts** - TLS, load balancing, health checks
3. **Networking has layers** - Public vs private, proxy vs direct
4. **Flycast is for internal load balancing** - Uses port 80, not your internal port
5. **Secrets stay secret** - Use `flyctl secrets`, never commit them
6. **Auto-stop saves money** - But only works for public traffic

---

## Useful Commands

```bash
# Check app status
flyctl status --app sparkyfitness

# View logs
flyctl logs --app sparkyfitness-server

# SSH into a machine
flyctl ssh console --app sparkyfitness

# List all apps
flyctl apps list

# Check secrets (names only, not values)
flyctl secrets list --app sparkyfitness-server

# Manually start a stopped machine
flyctl machine start <machine-id> --app sparkyfitness-server
```

---

## Resources

- [Fly.io Documentation](https://fly.io/docs/)
- [Docker Getting Started](https://docs.docker.com/get-started/)
- [SparkyFitness GitHub](https://github.com/codeWithCJ/SparkyFitness)
- [Fly.io Networking](https://fly.io/docs/networking/)
- [fly.toml Reference](https://fly.io/docs/reference/configuration/)
