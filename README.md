# SDNCheck PA 🇵🇦

Automated SDN/OFAC sanctions screening for Panama compliance professionals.

## Architecture

- **Frontend**: React (port 3000)
- **Backend**: Python FastAPI (port 8000)
- **Database**: PostgreSQL (port 5432)

## Tech Stack

- React 18
- Python 3.11 + FastAPI
- PostgreSQL 15
- Docker & Docker Compose
- Railway (deployment)

## Quick Start (Local Development)

### Prerequisites

- Docker and Docker Compose installed
- Git

### Run with Docker Compose

```bash
# Clone the repository
git clone https://github.com/develop4God/sdncheck.git
cd sdncheck

# Start all services
docker-compose up --build

# Access the application:
# - Frontend: http://localhost:3000
# - Backend API: http://localhost:8000
# - API Docs: http://localhost:8000/api/docs
```

### Stop Services

```bash
docker-compose down

# To also remove volumes (database data):
docker-compose down -v
```

## Deploy to Railway

Railway deployment uses a multi-service architecture with separate services for backend, frontend, and database.

### Prerequisites

- [Railway account](https://railway.app)
- GitHub repository connected to Railway

### Step 1: Create Railway Project

1. Go to [Railway Dashboard](https://railway.app/dashboard)
2. Click "New Project" → "Deploy from GitHub repo"
3. Select the `sdncheck` repository

### Step 2: Add PostgreSQL Database

1. In your Railway project, click "New Service" → "Database" → "PostgreSQL"
2. Railway will automatically create a PostgreSQL instance
3. The `DATABASE_URL` environment variable will be available for other services

### Step 3: Deploy Backend Service

1. Click "New Service" → "GitHub Repo" → Select `sdncheck`
2. Configure the service:
   - **Name**: `backend`
   - **Root Directory**: `/` (leave empty for root)
   - **Dockerfile Path**: `Dockerfile`

3. Set environment variables in the "Variables" tab:
   ```
   PORT=${{PORT}}
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   CORS_ORIGINS=https://your-frontend.up.railway.app,https://*.up.railway.app
   API_HOST=0.0.0.0
   ```

4. Railway will auto-detect the Dockerfile and deploy

### Step 4: Deploy Frontend Service

1. Click "New Service" → "GitHub Repo" → Select `sdncheck`
2. Configure the service:
   - **Name**: `frontend`
   - **Root Directory**: `frontend`
   - **Dockerfile Path**: `frontend/Dockerfile`

3. Set build arguments in "Variables" tab:
   ```
   REACT_APP_API_URL=https://your-backend.up.railway.app
   ```

4. After backend deploys, update `REACT_APP_API_URL` with the actual backend URL

### Step 5: Configure Networking

1. For each service, go to "Settings" → "Networking"
2. Click "Generate Domain" to create a public URL
3. Update the frontend's `REACT_APP_API_URL` with the backend's domain
4. Update the backend's `CORS_ORIGINS` with the frontend's domain

### Railway Environment Variables Reference

#### Backend Service

| Variable | Description | Example |
|----------|-------------|---------|
| `PORT` | Auto-provided by Railway | `${{PORT}}` |
| `DATABASE_URL` | PostgreSQL connection string | `${{Postgres.DATABASE_URL}}` |
| `CORS_ORIGINS` | Allowed frontend origins | `https://frontend.up.railway.app` |
| `API_HOST` | API bind address | `0.0.0.0` |
| `API_KEY` | Optional API authentication | `your-secure-key` |

#### Frontend Service

| Variable | Description | Example |
|----------|-------------|---------|
| `REACT_APP_API_URL` | Backend API URL (build arg) | `https://backend.up.railway.app` |

### CORS Configuration for Railway

The backend supports wildcard CORS patterns for Railway's dynamic subdomains:

```bash
# Allow specific Railway subdomain
CORS_ORIGINS=https://sdncheck-frontend.up.railway.app

# Allow all Railway subdomains (development)
CORS_ORIGINS=https://*.up.railway.app

# Multiple origins
CORS_ORIGINS=https://frontend.up.railway.app,https://*.up.railway.app,http://localhost:3000
```

### Troubleshooting

1. **CORS errors**: Ensure `CORS_ORIGINS` includes your frontend's Railway URL
2. **Database connection**: Verify `DATABASE_URL` is linked from PostgreSQL service
3. **Port issues**: Railway provides `PORT` automatically - don't hardcode 8000
4. **Build failures**: Check that root directory and Dockerfile path are correct

### Local Development with Railway

You can use the `.env.railway.example` files as reference:
- Root: `.env.railway.example` - Backend configuration
- Frontend: `frontend/.env.railway.example` - Frontend configuration

## Environment Variables

### Backend (Required)

| Variable | Description | Default |
|----------|-------------|---------|
| `DB_HOST` | PostgreSQL host | `localhost` |
| `DB_PORT` | PostgreSQL port | `5432` |
| `DB_NAME` | Database name | `sdn_database` |
| `DB_USER` | Database user | `sdn_user` |
| `DB_PASSWORD` | Database password | `sdn_password` |
| `API_HOST` | API bind host | `0.0.0.0` |
| `API_PORT` | API port | `8000` |
| `CORS_ORIGINS` | Allowed CORS origins | `http://localhost:3000` |

### Backend (Optional)

| Variable | Description | Default |
|----------|-------------|---------|
| `API_KEY` | API key for protected endpoints | (disabled) |
| `DATA_DIR` | Sanctions data directory | `sanctions_data` |
| `CONFIG_PATH` | Config file path | `config.yaml` |

### Frontend

| Variable | Description | Default |
|----------|-------------|---------|
| `REACT_APP_API_URL` | Backend API URL | `http://localhost:8000` |

## API Endpoints

- `GET /api/v1/health` - Health check
- `POST /api/v1/screen` - Screen individual
- `POST /api/v1/screen/bulk` - Bulk screening (CSV)
- `POST /api/v1/data/update` - Update sanctions data
- `GET /api/docs` - Swagger documentation

## Embedding Logo in HTML Reports

The audit log HTML report includes a logo at the top, embedded as a base64 PNG image. To update:

1. Replace the base64 string in `python/logo_base64.txt` with your own PNG logo
2. The logo will appear automatically in all generated HTML reports

## License

Proprietary - SDNCheck Panama © 2025

---

SDNCheck - Professional SDN screening for Panama 🚀
