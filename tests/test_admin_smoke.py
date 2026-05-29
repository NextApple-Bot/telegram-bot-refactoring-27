import pytest
from starlette.testclient import TestClient

from web_admin.main import app as admin_app


@pytest.fixture(scope="module")
def client():
    return TestClient(admin_app)


def test_login_page(client):
    response = client.get("/admin/auth/login")
    assert response.status_code == 200
    assert "Вход в админку" in response.text


def test_login_failure(client):
    response = client.post("/admin/auth/login", data={"password": "wrong"})
    assert response.status_code == 200
    assert "Неверный пароль" in response.text


def test_login_success(client):
    response = client.post("/admin/auth/login", data={"password": "testpass"})
    assert response.status_code == 303
    assert "/admin/dashboard" in response.headers.get("location", "")


def test_dashboard_redirect_when_not_authenticated(client):
    response = client.get("/admin/dashboard", follow_redirects=False)
    assert response.status_code in (307, 303)


def test_dashboard_authenticated(client):
    with client:
        client.post("/admin/auth/login", data={"password": "testpass"})
        response = client.get("/admin/dashboard")
        assert response.status_code == 200
        assert "Дашборд" in response.text


def test_clients_page_authenticated(client):
    with client:
        client.post("/admin/auth/login", data={"password": "testpass"})
        response = client.get("/admin/clients")
        assert response.status_code == 200
        assert "Клиенты" in response.text


def test_assortment_page_authenticated(client):
    with client:
        client.post("/admin/auth/login", data={"password": "testpass"})
        response = client.get("/admin/assortment")
        assert response.status_code == 200
        assert "Ассортимент" in response.text


def test_sold_page_authenticated(client):
    with client:
        client.post("/admin/auth/login", data={"password": "testpass"})
        response = client.get("/admin/sold")
        assert response.status_code == 200
        assert "Проданные товары" in response.text


def test_stats_page_authenticated(client):
    with client:
        client.post("/admin/auth/login", data={"password": "testpass"})
        response = client.get("/admin/stats")
        assert response.status_code == 200
        assert "Статистика" in response.text


def test_logout(client):
    with client:
        client.post("/admin/auth/login", data={"password": "testpass"})
        response = client.get("/admin/auth/logout", follow_redirects=False)
        assert response.status_code == 303
