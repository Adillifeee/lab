import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.database.db import get_session
from app.database.models import Address, Client, DeliveryService, Employee, Role, User
from app.main import app
from app.security import hash_password


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def get_test_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    with Session(engine) as session:
        admin_role = Role(name="admin")
        manager_role = Role(name="manager")
        courier_role = Role(name="courier")
        session.add_all([admin_role, manager_role, courier_role])
        session.commit()
        session.refresh(admin_role)
        session.refresh(manager_role)
        session.add(User(username="manager", password_hash=hash_password("Manager123!"), role_id=manager_role.id))
        sender = Client(full_name="Sender One", phone="+77001110000")
        recipient = Client(full_name="Receiver Two", phone="+77002220000")
        session.add_all([sender, recipient])
        session.commit()
        session.refresh(sender)
        session.refresh(recipient)
        session.add_all([
            Address(client_id=sender.id, city="Almaty", street="Abay", building="1"),
            Address(client_id=recipient.id, city="Almaty", street="Dostyk", building="2"),
            DeliveryService(code="STD", name="Standard", base_price=900, price_per_km=80),
        ])
        session.commit()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


def manager_token(client: TestClient) -> str:
    response = client.post("/auth/login", json={"username": "manager", "password": "Manager123!"})
    assert response.status_code == 200
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_authentication_is_required(client: TestClient):
    assert client.get("/orders").status_code == 401
    token = manager_token(client)
    assert client.get("/auth/me", headers=auth(token)).json()["role"] == "manager"


def test_create_order_calculates_price_and_records_status(client: TestClient):
    token = manager_token(client)
    payload = {"sender_client_id": 1, "recipient_client_id": 2, "sender_address_id": 1,
               "recipient_address_id": 2, "service_id": 1, "distance_km": 5, "weight_kg": 2,
               "description": "Documents"}
    response = client.post("/orders", json=payload, headers=auth(token))
    assert response.status_code == 201
    assert response.json()["total_price"] == 1500
    order_id = response.json()["id"]
    assert client.get(f"/orders/{order_id}/history", headers=auth(token)).json()[0]["new_status"] == "new"


def test_order_search_and_transition_validation(client: TestClient):
    token = manager_token(client)
    payload = {"sender_client_id": 1, "recipient_client_id": 2, "sender_address_id": 1,
               "recipient_address_id": 2, "service_id": 1}
    order = client.post("/orders", json=payload, headers=auth(token)).json()
    assert len(client.get("/orders", params={"q": "+77001110000"}, headers=auth(token)).json()) == 1
    response = client.patch(f'/orders/{order["id"]}/status', json={"status": "delivered"}, headers=auth(token))
    assert response.status_code == 409
    response = client.patch(f'/orders/{order["id"]}/status', json={"status": "confirmed"}, headers=auth(token))
    assert response.status_code == 200


def test_report_requires_manager_or_admin(client: TestClient):
    token = manager_token(client)
    assert client.get("/reports/summary", headers=auth(token)).status_code == 200
