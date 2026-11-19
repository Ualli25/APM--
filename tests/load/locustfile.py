"""Read-only Locust scenario for the local academic-council API."""
from locust import HttpUser, between, task


class SecretaryApiUser(HttpUser):
    wait_time = between(0.5, 1.5)

    @task(5)
    def list_members(self):
        self.client.get("/api/members", name="GET /api/members")

    @task(3)
    def list_councils(self):
        self.client.get("/api/councils", name="GET /api/councils")

    @task(2)
    def check_health(self):
        self.client.get("/health", name="GET /health")
