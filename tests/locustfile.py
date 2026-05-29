from locust import HttpUser, between, task


class AdminUser(HttpUser):
    wait_time = between(1, 3)
    host = "http://localhost:8000"

    def on_start(self):
        self.client.post("/admin/auth/login", data={"password": "testpass"})

    @task(3)
    def dashboard(self):
        self.client.get("/admin/dashboard/")

    @task(2)
    def assortment(self):
        self.client.get("/admin/assortment/")

    @task(1)
    def clients(self):
        self.client.get("/admin/clients/")
