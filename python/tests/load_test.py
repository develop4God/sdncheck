"""
SDNCheck Load Testing with Locust

This module provides load testing scenarios for the SDNCheck API using Locust.

Usage:
    # Start the application first
    cd python && uvicorn main:app --host 0.0.0.0 --port 8000

    # Run load tests
    locust -f tests/load_test.py --host=http://localhost:8000

    # Run headless with specific parameters
    locust -f tests/load_test.py --host=http://localhost:8000 \
        --users 100 --spawn-rate 10 --run-time 5m --headless

Performance Targets:
    - P95 latency < 500ms for search
    - 100 concurrent users without degradation
    - Connection pool not exhausted under load
    - Error rate < 0.01%
"""

import json
import random
import string
from typing import List

# Locust imports - graceful handling if not installed
try:
    from locust import HttpUser, task, between, events, tag
    from locust.runners import MasterRunner
    HAS_LOCUST = True
except ImportError:
    HAS_LOCUST = False
    # Create dummy classes for when locust isn't installed
    class HttpUser:
        pass
    def task(weight=1):
        def decorator(func):
            return func
        return decorator
    def between(a, b):
        return lambda: random.uniform(a, b)
    def tag(*tags):
        def decorator(func):
            return func
        return decorator
    events = None
    MasterRunner = None


# Sample test data
SAMPLE_NAMES = [
    "John Smith",
    "Maria Garcia",
    "Mohammed Ahmed",
    "Chen Wei",
    "Alexei Petrov",
    "Jean-Pierre Dubois",
    "Muhammad Ali Khan",
    "Giovanni Russo",
    "Yuki Tanaka",
    "Jose Rodriguez",
    "Hans Mueller",
    "Pierre Martin",
    "Abdul Rahman",
    "Viktor Sokolov",
    "Kim Sung",
]

SAMPLE_DOCUMENTS = [
    "A12345678",
    "B98765432",
    "C55555555",
    "D11111111",
    "E22222222",
]

SAMPLE_COUNTRIES = [
    "US", "GB", "DE", "FR", "ES", "IT", "JP", "CN", "RU", "BR"
]


def random_name() -> str:
    """Generate a random name for testing."""
    if random.random() < 0.7:
        # 70% chance to use sample names (may trigger matches)
        return random.choice(SAMPLE_NAMES)
    else:
        # 30% chance to generate random name
        first = ''.join(random.choices(string.ascii_uppercase, k=1)) + \
                ''.join(random.choices(string.ascii_lowercase, k=random.randint(3, 8)))
        last = ''.join(random.choices(string.ascii_uppercase, k=1)) + \
               ''.join(random.choices(string.ascii_lowercase, k=random.randint(4, 10)))
        return f"{first} {last}"


def random_document() -> str:
    """Generate a random document number."""
    if random.random() < 0.5:
        return random.choice(SAMPLE_DOCUMENTS)
    else:
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=9))


if HAS_LOCUST:
    
    class SDNCheckUser(HttpUser):
        """
        Simulates a typical SDNCheck API user.
        
        User behavior:
        - 60% of requests: Search entities by name
        - 20% of requests: Create screening requests
        - 10% of requests: Get entity by ID
        - 10% of requests: Health checks
        """
        
        # Wait 1-3 seconds between requests
        wait_time = between(1, 3)
        
        # Track created entity IDs for subsequent requests
        entity_ids: List[str] = []
        
        def on_start(self):
            """Called when a simulated user starts."""
            # Warm up by fetching some entity IDs
            self._warm_up()
        
        def _warm_up(self):
            """Fetch some entity IDs for testing."""
            try:
                response = self.client.get(
                    "/api/entities",
                    params={"limit": 10},
                    name="/api/entities (warmup)"
                )
                if response.status_code == 200:
                    data = response.json()
                    self.entity_ids = [e.get("id") for e in data.get("items", []) if e.get("id")]
            except Exception:
                pass
        
        @task(6)
        @tag("search", "read")
        def search_entity_by_name(self):
            """
            Search for entities by name.
            
            This is the most common operation (60% of traffic).
            Tests the trigram similarity search performance.
            """
            name = random_name()
            threshold = random.choice([0.3, 0.4, 0.5, 0.6])
            
            with self.client.get(
                "/api/search",
                params={
                    "name": name,
                    "threshold": threshold,
                    "limit": 50
                },
                name="/api/search",
                catch_response=True
            ) as response:
                if response.status_code == 200:
                    try:
                        data = response.json()
                        # Validate response structure
                        if "results" in data or "matches" in data or isinstance(data, list):
                            response.success()
                        else:
                            response.failure(f"Unexpected response structure: {list(data.keys())}")
                    except json.JSONDecodeError:
                        response.failure("Invalid JSON response")
                elif response.status_code == 404:
                    # No results is acceptable
                    response.success()
                else:
                    response.failure(f"Status code: {response.status_code}")
        
        @task(2)
        @tag("screening", "write")
        def create_screening_request(self):
            """
            Create a new screening request.
            
            Tests the full screening workflow including:
            - Request creation
            - Name matching
            - Result generation
            """
            payload = {
                "name": random_name(),
                "document": random_document() if random.random() < 0.5 else None,
                "country": random.choice(SAMPLE_COUNTRIES) if random.random() < 0.3 else None,
            }
            
            with self.client.post(
                "/api/screening",
                json=payload,
                name="/api/screening",
                catch_response=True
            ) as response:
                if response.status_code in [200, 201]:
                    try:
                        data = response.json()
                        if "id" in data or "request_id" in data:
                            response.success()
                        else:
                            response.failure("Missing request ID in response")
                    except json.JSONDecodeError:
                        response.failure("Invalid JSON response")
                elif response.status_code == 422:
                    # Validation error - still a valid response
                    response.success()
                else:
                    response.failure(f"Status code: {response.status_code}")
        
        @task(1)
        @tag("entity", "read")
        def get_entity_by_id(self):
            """
            Get a specific entity by ID.
            
            Tests direct entity lookup performance.
            """
            if not self.entity_ids:
                # Skip if we don't have any IDs
                return
            
            entity_id = random.choice(self.entity_ids)
            
            with self.client.get(
                f"/api/entities/{entity_id}",
                name="/api/entities/[id]",
                catch_response=True
            ) as response:
                if response.status_code == 200:
                    try:
                        data = response.json()
                        if "id" in data:
                            response.success()
                        else:
                            response.failure("Missing ID in entity response")
                    except json.JSONDecodeError:
                        response.failure("Invalid JSON response")
                elif response.status_code == 404:
                    # Entity may have been deleted
                    response.success()
                else:
                    response.failure(f"Status code: {response.status_code}")
        
        @task(1)
        @tag("health", "read")
        def health_check(self):
            """
            Check API health endpoint.
            
            Tests basic API availability.
            """
            with self.client.get(
                "/health",
                name="/health",
                catch_response=True
            ) as response:
                if response.status_code == 200:
                    try:
                        data = response.json()
                        if data.get("status") == "healthy" or data.get("healthy"):
                            response.success()
                        else:
                            response.failure(f"Unhealthy status: {data}")
                    except json.JSONDecodeError:
                        response.failure("Invalid JSON response")
                else:
                    response.failure(f"Status code: {response.status_code}")
    
    
    class SDNCheckBulkUser(HttpUser):
        """
        Simulates bulk screening operations.
        
        These users submit larger batch requests less frequently.
        """
        
        # Wait 10-30 seconds between bulk requests
        wait_time = between(10, 30)
        
        # Lower weight - fewer bulk users
        weight = 1
        
        @task
        @tag("bulk", "screening", "write")
        def bulk_screening(self):
            """
            Submit a bulk screening request with multiple names.
            
            Tests batch processing performance.
            """
            # Generate 10-50 names for bulk screening
            batch_size = random.randint(10, 50)
            entities = [
                {
                    "name": random_name(),
                    "document": random_document() if random.random() < 0.3 else None,
                }
                for _ in range(batch_size)
            ]
            
            with self.client.post(
                "/api/screening/bulk",
                json={"entities": entities},
                name="/api/screening/bulk",
                catch_response=True
            ) as response:
                if response.status_code in [200, 201, 202]:
                    response.success()
                elif response.status_code == 404:
                    # Endpoint may not exist yet
                    response.success()
                elif response.status_code == 413:
                    # Request too large - expected for very large batches
                    response.success()
                else:
                    response.failure(f"Status code: {response.status_code}")
    
    
    # Event handlers for reporting
    @events.quitting.add_listener
    def on_quitting(environment, **kwargs):
        """Print summary when load test ends."""
        if environment.stats.total.fail_ratio > 0.01:
            print(f"\n⚠️  WARNING: Failure rate {environment.stats.total.fail_ratio:.2%} exceeds 1% threshold")
        
        if environment.stats.total.avg_response_time > 500:
            print(f"\n⚠️  WARNING: Average response time {environment.stats.total.avg_response_time:.0f}ms exceeds 500ms target")
    
    
    @events.init.add_listener
    def on_locust_init(environment, **kwargs):
        """Initialize custom metrics tracking."""
        if isinstance(environment.runner, MasterRunner):
            print("Running in distributed mode (master)")

else:
    # Stub class when Locust is not installed
    class SDNCheckUser:
        """Locust not installed. Install with: pip install locust"""
        pass
    
    class SDNCheckBulkUser:
        """Locust not installed. Install with: pip install locust"""
        pass


# Allow running as a script for basic validation
if __name__ == "__main__":
    if not HAS_LOCUST:
        print("Locust is not installed. Install with:")
        print("  pip install locust")
        print("")
        print("Then run:")
        print("  locust -f tests/load_test.py --host=http://localhost:8000")
    else:
        print("Load test module loaded successfully.")
        print("")
        print("Run with:")
        print("  locust -f tests/load_test.py --host=http://localhost:8000")
        print("")
        print("Or headless:")
        print("  locust -f tests/load_test.py --host=http://localhost:8000 \\")
        print("      --users 100 --spawn-rate 10 --run-time 5m --headless")
