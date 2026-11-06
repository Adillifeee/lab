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


class Client(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    full_name: str = Field(index=True, max_length=180)
    phone: str = Field(index=True, unique=True, max_length=40)
    email: str = Field(default="", max_length=254)
    created_at: datetime = Field(default_factory=utc_now)
    addresses: list["Address"] = Relationship(back_populates="client")


class Employee(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    full_name: str = Field(index=True, max_length=180)
    phone: str = Field(index=True, max_length=40)
    position: str = Field(default="Сотрудник", max_length=80)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", unique=True)
    is_active: bool = True
    user: Optional[User] = Relationship(back_populates="employee")


class Vehicle(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    plate_number: str = Field(unique=True, index=True, max_length=30)
    vehicle_type: str = Field(default="Велосипед", max_length=60)
    capacity_kg: float = Field(default=20, gt=0)
    is_active: bool = True


class DeliveryService(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(unique=True, index=True, max_length=30)
    name: str = Field(index=True, max_length=100)
    description: str = Field(default="", max_length=500)
    base_price: float = Field(ge=0)
    price_per_km: float = Field(default=0, ge=0)
    estimated_hours: int = Field(default=24, gt=0)
    is_active: bool = True


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


class DeliveryRoute(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(unique=True, index=True, max_length=40)
    name: str = Field(max_length=120)
    planned_date: datetime = Field(index=True)
    courier_id: Optional[int] = Field(default=None, foreign_key="employee.id", index=True)
    vehicle_id: Optional[int] = Field(default=None, foreign_key="vehicle.id")
    status: str = Field(default="planned", index=True, max_length=30)
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


class Parcel(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="deliveryorder.id", index=True)
    description: str = Field(max_length=250)
    weight_kg: float = Field(default=0, ge=0)
    length_cm: float = Field(default=0, ge=0)
    width_cm: float = Field(default=0, ge=0)
    height_cm: float = Field(default=0, ge=0)


class RouteStop(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    route_id: int = Field(foreign_key="deliveryroute.id", index=True)
    order_id: int = Field(foreign_key="deliveryorder.id", index=True)
    sequence: int = Field(gt=0)
    completed_at: Optional[datetime] = None
    route: DeliveryRoute = Relationship(back_populates="stops")


class Assignment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="deliveryorder.id", index=True)
    courier_id: int = Field(foreign_key="employee.id", index=True)
    assigned_by_user_id: int = Field(foreign_key="user.id")
    assigned_at: datetime = Field(default_factory=utc_now)
    active: bool = True


class StatusHistory(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="deliveryorder.id", index=True)
    old_status: str = Field(default="", max_length=30)
    new_status: str = Field(max_length=30)
    changed_by_user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    changed_at: datetime = Field(default_factory=utc_now, index=True)
    comment: str = Field(default="", max_length=300)


class Payment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="deliveryorder.id", index=True)
    amount: float = Field(gt=0)
    method: str = Field(default="cash", max_length=30)
    status: str = Field(default="paid", max_length=30)
    paid_at: datetime = Field(default_factory=utc_now)
    reference: str = Field(default="", max_length=100)


class Review(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="deliveryorder.id", unique=True, index=True)
    client_id: int = Field(foreign_key="client.id", index=True)
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=1000)
    created_at: datetime = Field(default_factory=utc_now)
