from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Role(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True, max_length=40)
    description: str = Field(default="", max_length=250)
    users: list["User"] = Relationship(back_populates="role")


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True, max_length=80)
    password_hash: str = Field(max_length=300)
    role_id: int = Field(foreign_key="role.id", index=True)
    is_active: bool = True
    role: Role = Relationship(back_populates="users")
    employee: Optional["Employee"] = Relationship(back_populates="user")
    assignments_made: list["Assignment"] = Relationship(back_populates="assigned_by")
    status_changes: list["StatusHistory"] = Relationship(back_populates="changed_by")


class Client(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    full_name: str = Field(index=True, max_length=180)
    phone: str = Field(index=True, unique=True, max_length=40)
    email: str = Field(default="", max_length=254)
    created_at: datetime = Field(default_factory=utc_now)
    addresses: list["Address"] = Relationship(back_populates="client")
    sent_orders: list["DeliveryOrder"] = Relationship(
        back_populates="sender",
        sa_relationship_kwargs={"foreign_keys": "DeliveryOrder.sender_client_id"},
    )
    received_orders: list["DeliveryOrder"] = Relationship(
        back_populates="recipient",
        sa_relationship_kwargs={"foreign_keys": "DeliveryOrder.recipient_client_id"},
    )
    reviews: list["Review"] = Relationship(back_populates="client")


class Employee(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    full_name: str = Field(index=True, max_length=180)
    phone: str = Field(index=True, max_length=40)
    position: str = Field(default="Сотрудник", max_length=80)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", unique=True)
    is_active: bool = True
    user: Optional[User] = Relationship(back_populates="employee")
    routes: list["DeliveryRoute"] = Relationship(
        back_populates="courier",
        sa_relationship_kwargs={"foreign_keys": "DeliveryRoute.courier_id"},
    )
    delivery_orders: list["DeliveryOrder"] = Relationship(
        back_populates="courier",
        sa_relationship_kwargs={"foreign_keys": "DeliveryOrder.courier_id"},
    )
    assignments: list["Assignment"] = Relationship(back_populates="courier")


class Vehicle(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    plate_number: str = Field(unique=True, index=True, max_length=30)
    vehicle_type: str = Field(default="Велосипед", max_length=60)
    capacity_kg: float = Field(default=20, gt=0)
    is_active: bool = True
    routes: list["DeliveryRoute"] = Relationship(back_populates="vehicle")


class DeliveryService(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(unique=True, index=True, max_length=30)
    name: str = Field(index=True, max_length=100)
    description: str = Field(default="", max_length=500)
    base_price: float = Field(ge=0)
    price_per_km: float = Field(default=0, ge=0)
    estimated_hours: int = Field(default=24, gt=0)
    is_active: bool = True
    orders: list["DeliveryOrder"] = Relationship(back_populates="service")


class Address(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    client_id: int = Field(foreign_key="client.id", index=True)
    label: str = Field(default="Основной", max_length=60)
    city: str = Field(index=True, max_length=100)
    street: str = Field(max_length=180)
    building: str = Field(max_length=40)
    apartment: str = Field(default="", max_length=40)
    instructions: str = Field(default="", max_length=300)
    client: Client = Relationship(back_populates="addresses")
    sender_orders: list["DeliveryOrder"] = Relationship(
        back_populates="sender_address",
        sa_relationship_kwargs={"foreign_keys": "DeliveryOrder.sender_address_id"},
    )
    recipient_orders: list["DeliveryOrder"] = Relationship(
        back_populates="recipient_address",
        sa_relationship_kwargs={"foreign_keys": "DeliveryOrder.recipient_address_id"},
    )


class DeliveryRoute(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(unique=True, index=True, max_length=40)
    name: str = Field(max_length=120)
    planned_date: datetime = Field(index=True)
    courier_id: Optional[int] = Field(default=None, foreign_key="employee.id", index=True)
    vehicle_id: Optional[int] = Field(default=None, foreign_key="vehicle.id")
    status: str = Field(default="planned", index=True, max_length=30)
    courier: Optional[Employee] = Relationship(
        back_populates="routes",
        sa_relationship_kwargs={"foreign_keys": "DeliveryRoute.courier_id"},
    )
    vehicle: Optional[Vehicle] = Relationship(back_populates="routes")
    orders: list["DeliveryOrder"] = Relationship(back_populates="route")
    stops: list["RouteStop"] = Relationship(back_populates="route")


class DeliveryOrder(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_number: str = Field(unique=True, index=True, max_length=40)
    sender_client_id: int = Field(foreign_key="client.id", index=True)
    recipient_client_id: int = Field(foreign_key="client.id", index=True)
    sender_address_id: int = Field(foreign_key="address.id")
    recipient_address_id: int = Field(foreign_key="address.id")
    service_id: int = Field(foreign_key="deliveryservice.id", index=True)
    route_id: Optional[int] = Field(default=None, foreign_key="deliveryroute.id", index=True)
    courier_id: Optional[int] = Field(default=None, foreign_key="employee.id", index=True)
    status: str = Field(default="new", index=True, max_length=30)
    distance_km: float = Field(default=0, ge=0)
    weight_kg: float = Field(default=0, ge=0)
    description: str = Field(default="", max_length=500)
    declared_value: float = Field(default=0, ge=0)
    discount: float = Field(default=0, ge=0)
    total_price: float = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utc_now, index=True)
    scheduled_at: Optional[datetime] = Field(default=None, index=True)
    delivered_at: Optional[datetime] = None
    sender: Client = Relationship(
        back_populates="sent_orders",
        sa_relationship_kwargs={"foreign_keys": "DeliveryOrder.sender_client_id"},
    )
    recipient: Client = Relationship(
        back_populates="received_orders",
        sa_relationship_kwargs={"foreign_keys": "DeliveryOrder.recipient_client_id"},
    )
    sender_address: Address = Relationship(
        back_populates="sender_orders",
        sa_relationship_kwargs={"foreign_keys": "DeliveryOrder.sender_address_id"},
    )
    recipient_address: Address = Relationship(
        back_populates="recipient_orders",
        sa_relationship_kwargs={"foreign_keys": "DeliveryOrder.recipient_address_id"},
    )
    service: DeliveryService = Relationship(back_populates="orders")
    route: Optional[DeliveryRoute] = Relationship(back_populates="orders")
    courier: Optional[Employee] = Relationship(
        back_populates="delivery_orders",
        sa_relationship_kwargs={"foreign_keys": "DeliveryOrder.courier_id"},
    )
    parcels: list["Parcel"] = Relationship(back_populates="order")
    route_stops: list["RouteStop"] = Relationship(back_populates="order")
    assignments: list["Assignment"] = Relationship(back_populates="order")
    status_history: list["StatusHistory"] = Relationship(back_populates="order")
    payments: list["Payment"] = Relationship(back_populates="order")
    review: Optional["Review"] = Relationship(back_populates="order")


class Parcel(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="deliveryorder.id", index=True)
    description: str = Field(max_length=250)
    weight_kg: float = Field(default=0, ge=0)
    length_cm: float = Field(default=0, ge=0)
    width_cm: float = Field(default=0, ge=0)
    height_cm: float = Field(default=0, ge=0)
    order: DeliveryOrder = Relationship(back_populates="parcels")


class RouteStop(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    route_id: int = Field(foreign_key="deliveryroute.id", index=True)
    order_id: int = Field(foreign_key="deliveryorder.id", index=True)
    sequence: int = Field(gt=0)
    completed_at: Optional[datetime] = None
    route: DeliveryRoute = Relationship(back_populates="stops")
    order: DeliveryOrder = Relationship(back_populates="route_stops")


class Assignment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="deliveryorder.id", index=True)
    courier_id: int = Field(foreign_key="employee.id", index=True)
    assigned_by_user_id: int = Field(foreign_key="user.id")
    assigned_at: datetime = Field(default_factory=utc_now)
    active: bool = True
    order: DeliveryOrder = Relationship(back_populates="assignments")
    courier: Employee = Relationship(back_populates="assignments")
    assigned_by: User = Relationship(back_populates="assignments_made")


class StatusHistory(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="deliveryorder.id", index=True)
    old_status: str = Field(default="", max_length=30)
    new_status: str = Field(max_length=30)
    changed_by_user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    changed_at: datetime = Field(default_factory=utc_now, index=True)
    comment: str = Field(default="", max_length=300)
    order: DeliveryOrder = Relationship(back_populates="status_history")
    changed_by: Optional[User] = Relationship(back_populates="status_changes")


class Payment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="deliveryorder.id", index=True)
    amount: float = Field(gt=0)
    method: str = Field(default="cash", max_length=30)
    status: str = Field(default="paid", max_length=30)
    paid_at: datetime = Field(default_factory=utc_now)
    reference: str = Field(default="", max_length=100)
    order: DeliveryOrder = Relationship(back_populates="payments")


class Review(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="deliveryorder.id", unique=True, index=True)
    client_id: int = Field(foreign_key="client.id", index=True)
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=1000)
    created_at: datetime = Field(default_factory=utc_now)
    order: DeliveryOrder = Relationship(back_populates="review")
    client: Client = Relationship(back_populates="reviews")
