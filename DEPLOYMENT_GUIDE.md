# SparkyFitness Fly.io Deployment Guide

A guide explaining how we deployed SparkyFitness to Fly.io, covering Docker, networking, and cloud deployment concepts.

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Docker Basics](#docker-basics)
3. [Fly.io Concepts](#flyio-concepts)
4. [The Deployment Process](#the-deployment-process)
5. [Networking Deep Dive](#networking-deep-dive)
6. [Configuration Files](#configuration-files)
7. [Updating Your Deployment](#updating-your-deployment)

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

Think of it like shipping containers for software. Just like how shipping containers standardized global trade (any container fits on any ship/truck/train), Docker containers standardize software deployment (any container runs on any Docker host).

**Key concepts:**
- **Image**: A read-only template (like a snapshot of an app). Built from a Dockerfile.
- **Container**: A running instance of an image. You can have multiple containers from the same image.
- **Registry**: A place to store/share images (like DockerHub, or Fly.io's registry)
- **Dockerfile**: Instructions to build an image from source code

### Pre-built Images vs Building from Source

**Option 1: Pre-built Images**
```toml
[build]
  image = "codewithcj/sparkyfitness_server:latest"
```
Fly.io pulls the image directly from DockerHub. Fast, but you get whatever version was last published.

**Option 2: Build from Source (what we use)**
```toml
[build]
  dockerfile = "Dockerfile"
```
Fly.io (or your local Docker) builds the image from your source code. Slower, but you get the exact code you have locally.

**Why we build from source**: The pre-built DockerHub images can be outdated. For example, USDA food provider support was added to the codebase on Dec 16, 2025, but wasn't in the pre-built images yet. Building from source ensures you get the latest features.

---

## Fly.io Concepts

### What is Fly.io?

Fly.io runs your Docker containers on servers worldwide. It's simpler than AWS/GCP but more powerful than Heroku. You describe what you want in a `fly.toml` file, and Fly.io handles the rest.

**Key concepts:**

| Concept | What it is |
|---------|-----------|
| **App** | A deployed application (has a unique name like `sparkyfitness`) |
| **Machine** | A micro-VM running your container (like a tiny dedicated server) |
| **Region** | Physical datacenter location (e.g., `iad` = Ashburn, Virginia) |
| **Fly Proxy** | Load balancer that sits in front of your machines, handles TLS, routes traffic |

### Machines and Auto-scaling

Fly.io can automatically start/stop machines based on traffic to save money:

```toml
[http_service]
  auto_stop_machines = 'stop'    # Stop when idle (saves money)
  auto_start_machines = true     # Start when request comes in
  min_machines_running = 0       # Allow all machines to stop
```

**The catch**: Auto-start only works for traffic coming through the Fly Proxy (public requests). Internal traffic between your apps doesn't trigger auto-start.

For the backend, we disabled auto-stop because the frontend makes internal requests to it:

```toml
  auto_stop_machines = 'off'
  min_machines_running = 1       # Always keep 1 running
```

---

## The Deployment Process

### Step 1: Create the Database

```bash
flyctl postgres create --name sparkyfitness-db --region iad
```

This creates a managed Postgres cluster. Fly.io handles backups, failover, connection pooling, etc. You get a database without managing database servers.

### Step 2: Create the Apps

```bash
flyctl apps create sparkyfitness-server --org personal
flyctl apps create sparkyfitness --org personal
```

This reserves the app names and creates the apps in Fly.io's system, but doesn't deploy anything yet.

### Step 3: Attach Database to Backend

```bash
flyctl postgres attach sparkyfitness-db --app sparkyfitness-server
```

This does three things:
1. Creates a database user for the app
2. Sets the `DATABASE_URL` secret on the app (connection string)
3. Configures network access so the app can reach the database

### Step 4: Allocate Private IP for Flycast

```bash
flyctl ips allocate-v6 --private --app sparkyfitness-server
```

This enables Flycast networking, which we need for frontend→backend communication. More on this in [Networking Deep Dive](#networking-deep-dive).

### Step 5: Set Secrets

Secrets are encrypted environment variables that aren't stored in your code:

```bash
flyctl secrets set \
  SESSION_SECRET="your-random-string" \
  JWT_SECRET="another-random-string" \
  --app sparkyfitness-server
```

**Important**: Never put secrets in `fly.toml` - that file is committed to git! Use `flyctl secrets set` for anything sensitive.

### Step 6: Deploy

```bash
# Deploy backend
cd SparkyFitnessServer
flyctl deploy --ha=false --local-only

# Deploy frontend
cd ../SparkyFitnessFrontend
flyctl deploy --ha=false --local-only
```

**Flags explained:**
- `--ha=false`: Creates only 1 machine. Default is 2 for high availability, but that costs more.
- `--local-only`: Builds the Docker image on your machine instead of Fly.io's remote builders. More reliable, avoids registry authentication issues.

---

## Networking Deep Dive

This was the trickiest part of the deployment. Understanding Fly.io networking is crucial.

### Three Types of Hostnames

| Hostname | Example | Routes Through | Use Case |
|----------|---------|----------------|----------|
| `.fly.dev` | `sparkyfitness-server.fly.dev` | Public internet | External access from users |
| `.internal` | `sparkyfitness-server.internal` | Direct to machine | Same-org private traffic |
| `.flycast` | `sparkyfitness-server.flycast` | Fly Proxy (private) | Private load-balanced traffic |

### Why We Used Flycast

The frontend nginx needs to proxy API requests to the backend:

```
User → Frontend (nginx) → Backend
```

**Problem with `.internal`**:
- Nginx validates all DNS hostnames when it starts up
- The `.internal` DNS wasn't resolving during nginx config validation
- nginx failed to start with "host not found in upstream"

**Solution - Flycast**:
- Allocate a private IPv6 address: `flyctl ips allocate-v6 --private`
- Use `.flycast` hostname which resolves immediately via Fly's DNS
- Traffic still stays private (never leaves Fly.io's network)

### The Port 80 vs 3010 Gotcha

This one was confusing. Here's how Fly Proxy works:

```
                    ┌─────────────────┐
Internet (:443) ──► │   Fly Proxy     │ ──► Container (:3010)
                    │  (handles TLS)  │
                    └─────────────────┘
```

The Fly Proxy:
1. Listens on ports 80/443 (standard HTTP/HTTPS)
2. Terminates TLS (handles the HTTPS encryption)
3. Forwards plain HTTP to your container's `internal_port`

**Key insight**: Flycast also routes through the Fly Proxy! So when the frontend connects to `sparkyfitness-server.flycast`, it needs to use port 80 (what the proxy listens on), not port 3010 (what the container listens on).

```toml
# Wrong - Flycast doesn't expose port 3010
SPARKY_FITNESS_SERVER_PORT = "3010"

# Correct - Flycast routes through Fly Proxy on port 80
SPARKY_FITNESS_SERVER_PORT = "80"
```

### The force_https Setting

```toml
force_https = true   # Redirects HTTP → HTTPS
force_https = false  # Allows HTTP
```

We set `force_https = false` on the backend because:
- Internal Flycast traffic uses HTTP (TLS is unnecessary inside the private network)
- With `force_https = true`, the proxy returned 301 redirects that broke internal routing

The frontend keeps `force_https = true` because users should always use HTTPS.

---

## Configuration Files

### fly.toml (Backend)

```toml
app = 'sparkyfitness-server'
primary_region = 'iad'

[build]
  dockerfile = "Dockerfile"

[env]
  NODE_ENV = "production"
  SPARKY_FITNESS_SERVER_PORT = "3010"
  SPARKY_FITNESS_LOG_LEVEL = "INFO"
  TZ = "Etc/UTC"

[http_service]
  internal_port = 3010
  force_https = false
  auto_stop_machines = 'off'
  auto_start_machines = true
  min_machines_running = 1
  processes = ['app']

[[http_service.checks]]
  grace_period = "10s"
  interval = "30s"
  method = "GET"
  timeout = "5s"
  path = "/health"

[[vm]]
  memory = '512mb'
  cpu_kind = 'shared'
  cpus = 1
```

### fly.toml (Frontend)

```toml
app = 'sparkyfitness'
primary_region = 'iad'

[build]
  dockerfile = "Dockerfile"

[env]
  SPARKY_FITNESS_SERVER_HOST = "sparkyfitness-server.flycast"
  SPARKY_FITNESS_SERVER_PORT = "80"

[http_service]
  internal_port = 80
  force_https = true
  auto_stop_machines = 'stop'
  auto_start_machines = true
  min_machines_running = 0

[[http_service.checks]]
  grace_period = "10s"
  interval = "30s"
  method = "GET"
  timeout = "5s"
  path = "/"

[[vm]]
  memory = '256mb'
  cpu_kind = 'shared'
  cpus = 1
```

### nginx.conf.template (Frontend)

The frontend uses an nginx config template that substitutes environment variables at container startup. This lets us configure the backend hostname via `fly.toml` instead of hardcoding it.

```nginx
location /api/ {
  proxy_pass http://$SPARKY_FITNESS_SERVER_HOST:$SPARKY_FITNESS_SERVER_PORT/;
  proxy_set_header Host $host;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto $scheme;
  proxy_set_header X-Forwarded-Ssl on;
}
```

The Dockerfile uses `envsubst` to replace the environment variables when the container starts:

```dockerfile
CMD envsubst '$SPARKY_FITNESS_SERVER_HOST $SPARKY_FITNESS_SERVER_PORT' < /etc/nginx/nginx.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'
```

**Why specify which variables?** Nginx config uses `$uri`, `$host`, etc. as nginx variables. If we ran `envsubst` without specifying variables, it would try to replace those too and break the config.

---

## Updating Your Deployment

### Pull Latest from Upstream & Redeploy

```bash
# Get latest changes
git fetch upstream
git merge upstream/main

# Redeploy backend
cd SparkyFitnessServer
flyctl deploy --ha=false --local-only

# Redeploy frontend
cd ../SparkyFitnessFrontend
flyctl deploy --ha=false --local-only
```

### Useful Commands

```bash
# Check app status
flyctl status --app sparkyfitness

# View logs (streams live)
flyctl logs --app sparkyfitness-server

# SSH into a running machine
flyctl ssh console --app sparkyfitness

# List all your apps
flyctl apps list

# Check secrets (names only, not values)
flyctl secrets list --app sparkyfitness-server

# Manually start a stopped machine
flyctl machine start <machine-id> --app sparkyfitness-server
```

---

## Key Takeaways

1. **Build from source for latest features** - Pre-built DockerHub images may be outdated
2. **Fly.io handles the hard parts** - TLS termination, load balancing, health checks
3. **Networking has layers** - Public (`.fly.dev`) vs private (`.internal`, `.flycast`)
4. **Flycast uses port 80** - Not your internal port, because it routes through Fly Proxy
5. **Secrets stay secret** - Use `flyctl secrets set`, never commit them to git
6. **Auto-stop saves money** - But only works for public traffic, not internal
7. **Use `--local-only` for reliable builds** - Avoids remote builder auth issues

---

## Resources

- [Fly.io Documentation](https://fly.io/docs/)
- [Docker Getting Started](https://docs.docker.com/get-started/)
- [SparkyFitness GitHub](https://github.com/codeWithCJ/SparkyFitness)
- [Fly.io Networking](https://fly.io/docs/networking/)
- [Flycast Documentation](https://fly.io/docs/networking/flycast/)
- [fly.toml Reference](https://fly.io/docs/reference/configuration/)
