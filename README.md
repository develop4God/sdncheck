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

### Option 1: One-Click Deploy

1. Create a Railway account at [railway.app](https://railway.app)
2. Connect your GitHub repository
3. Railway will auto-detect the configuration

### Option 2: Manual Setup

1. Install Railway CLI:
   ```bash
   npm install -g @railway/cli
   ```

2. Login and link project:
   ```bash
   railway login
   railway init
   ```

3. Add PostgreSQL service:
   - In Railway dashboard, add a PostgreSQL plugin
   - Copy the `DATABASE_URL` to your backend service

4. Deploy:
   ```bash
   railway up
   ```

### Railway Services Setup

Create 3 services in Railway:

1. **Backend** (Python API)
   - Root directory: `/`
   - Dockerfile: `Dockerfile`
   - Environment variables: see below

2. **Frontend** (React)
   - Root directory: `/frontend`
   - Dockerfile: `/frontend/Dockerfile`
   - Build args: `REACT_APP_API_URL=https://your-backend-url.railway.app`

3. **Database** (PostgreSQL)
   - Add PostgreSQL from Railway plugins

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
