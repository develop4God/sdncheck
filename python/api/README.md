# Sanctions Screening API

FastAPI wrapper for the Python sanctions screening engine. Enables Electron frontend integration via REST API.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
cd python
uvicorn api.server:app --reload --port 8000

# Or with custom host/port
API_HOST=0.0.0.0 API_PORT=9000 uvicorn api.server:app --reload
```

## API Endpoints

### Screen Individual
```bash
POST /api/v1/screen

# Request
curl -X POST http://localhost:8000/api/v1/screen \
  -H "Content-Type: application/json" \
  -d '{"name": "Mohamed Ali"}'

# Response
{
  "screening_id": "uuid",
  "screening_date": "2025-01-15T10:30:00Z",
  "is_hit": true,
  "hit_count": 2,
  "matches": [...],
  "processing_time_ms": 45,
  "algorithm_version": "2.0.0"
}
```

### Bulk Screening
```bash
POST /api/v1/screen/bulk

# Upload CSV file
curl -X POST http://localhost:8000/api/v1/screen/bulk \
  -F "file=@input.csv"

# CSV format: nombre,cedula,pais
# Response includes total_processed, hits, hit_rate, results
```

### Health Check
```bash
GET /api/v1/health

# Returns entity count, data age, memory usage
```

### Update Data
```bash
POST /api/v1/data/update

# Downloads fresh OFAC and UN data, reloads screener
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_HOST` | `127.0.0.1` | Server bind address |
| `API_PORT` | `8000` | Server port |
| `DATA_DIR` | `sanctions_data` | Directory for XML files |
| `MAX_UPLOAD_SIZE_MB` | `10` | Max CSV upload size |
| `CONFIG_PATH` | `config.yaml` | Path to config file |

## API Documentation

- Swagger UI: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc
- OpenAPI JSON: http://localhost:8000/api/openapi.json

## Error Responses

All errors return consistent format:
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable description",
    "field": "name",
    "suggestion": "How to fix",
    "timestamp": "2025-01-15T10:30:00Z"
  }
}
```

## Testing

```bash
# Run all API tests
pytest tests/test_api.py -v

# Run specific test category
pytest tests/test_api.py -k "validation" -v

# Run with coverage
pytest tests/test_api.py --cov=api --cov-report=term-missing

# Skip slow tests
pytest tests/test_api.py -v -m "not slow"
```

## Security Features

- Input validation matches `config.yaml` rules
- All user input sanitized before logging
- CORS restricted to localhost origins
- File uploads limited to configured size
- SQL/XSS injection attempts blocked

## Files

```
api/
├── __init__.py       # Package marker
├── server.py         # FastAPI application and endpoints
├── models.py         # Pydantic request/response schemas
├── middleware.py     # CORS, logging, error handling
└── README.md         # This file
```
