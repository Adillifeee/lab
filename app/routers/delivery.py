from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.database.db import get_session
from app.database.models import (
    Address, Assignment, Client, DeliveryOrder, DeliveryRoute, DeliveryService,
    Employee, Parcel, Payment, Review, Role, RouteStop, StatusHistory, User, Vehicle,
)
from app.security import current_user, require_roles

router = APIRouter(tags=["delivery"])
STATUSES = {"new", "confirmed", "assigned", "in_transit", "delayed", "delivered", "paid", "closed", "cancelled"}
TRANSITIONS = {
    "new": {"confirmed", "cancelled"}, "confirmed": {"assigned", "cancelled"},
    "assigned": {"in_transit", "cancelled"}, "in_transit": {"delivered", "delayed"},
    "delayed": {"in_transit", "delivered", "cancelled"}, "delivered": {"paid", "closed"},
    "paid": {"closed"}, "closed": set(), "cancelled": set(),
}


class ClientInput(BaseModel):
    full_name: str = Field(min_length=2, max_length=180)
    phone: str = Field(min_length=5, max_length=40)
    email: str = ""


class EmployeeInput(BaseModel):
    full_name: str = Field(min_length=2, max_length=180)
    phone: str = Field(min_length=5, max_length=40)
    position: str = "Курьер"
    user_id: Optional[int] = None


class VehicleInput(BaseModel):
    plate_number: str = Field(min_length=3, max_length=30)
    vehicle_type: str
    capacity_kg: float = Field(gt=0)


class AddressInput(BaseModel):
    label: str = "Основной"
    city: str = "Алматы"
    street: str = Field(min_length=2, max_length=180)
    building: str = Field(min_length=1, max_length=40)
    apartment: str = ""
    instructions: str = ""


class ServiceInput(BaseModel):
    code: str = Field(min_length=2, max_length=30)
    name: str
    description: str = ""
    base_price: float = Field(ge=0)
    price_per_km: float = Field(default=0, ge=0)
    estimated_hours: int = Field(default=24, gt=0)


class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    base_price: Optional[float] = Field(default=None, ge=0)
    price_per_km: Optional[float] = Field(default=None, ge=0)
    estimated_hours: Optional[int] = Field(default=None, gt=0)
    is_active: Optional[bool] = None


class OrderInput(BaseModel):
    sender_client_id: int
    recipient_client_id: int
    sender_address_id: int
    recipient_address_id: int
    service_id: int
    distance_km: float = Field(default=0, ge=0)
    weight_kg: float = Field(default=0, ge=0)
    description: str = ""
    declared_value: float = Field(default=0, ge=0)
    discount: float = Field(default=0, ge=0)
    scheduled_at: Optional[datetime] = None


class StatusInput(BaseModel):
    status: str
    comment: str = ""


class AssignInput(BaseModel):
    courier_id: int
    route_id: Optional[int] = None


class RouteInput(BaseModel):
    code: str
    name: str
    planned_date: datetime
    courier_id: Optional[int] = None
    vehicle_id: Optional[int] = None


class RouteStopInput(BaseModel):
    order_id: int
    sequence: int = Field(gt=0)


class PaymentInput(BaseModel):
    amount: float = Field(gt=0)
    method: str = "cash"
    reference: str = ""


class ReviewInput(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = ""


class ParcelInput(BaseModel):
    description: str = Field(min_length=1, max_length=250)
    weight_kg: float = Field(default=0, ge=0)
    length_cm: float = Field(default=0, ge=0)
    width_cm: float = Field(default=0, ge=0)
    height_cm: float = Field(default=0, ge=0)


def record_status(session: Session, order: DeliveryOrder, new_status: str, user_id: Optional[int], comment: str = ""):
    old = order.status
    if new_status not in TRANSITIONS.get(old, set()):
        raise HTTPException(409, f"Invalid status transition: {old} -> {new_status}")
    order.status = new_status
    if new_status == "delivered":
        order.delivered_at = datetime.now(timezone.utc)
    session.add(StatusHistory(order_id=order.id, old_status=old, new_status=new_status, changed_by_user_id=user_id, comment=comment))


def ensure_order_access(order: DeliveryOrder, user: User, session: Session) -> None:
    role = session.get(Role, user.role_id)
    if role and role.name == "courier":
        employee = session.exec(select(Employee).where(Employee.user_id == user.id)).first()
        if not employee or order.courier_id != employee.id:
            raise HTTPException(403, "Courier can access only assigned orders")


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/clients", response_model=list[Client])
def clients(q: Optional[str] = None, session: Session = Depends(get_session), _: User = Depends(require_roles("admin", "manager"))):
    stmt = select(Client)
    if q:
        stmt = stmt.where((Client.full_name.contains(q)) | (Client.phone.contains(q)))
    return session.exec(stmt.order_by(Client.full_name).limit(500)).all()


@router.post("/clients", response_model=Client, status_code=201)
def create_client(data: ClientInput, session: Session = Depends(get_session), _: User = Depends(require_roles("admin", "manager"))):
    if session.exec(select(Client).where(Client.phone == data.phone)).first():
        raise HTTPException(409, "Client phone already exists")
    client = Client(**data.model_dump())
    session.add(client)
    session.commit()
    session.refresh(client)
    return client


@router.get("/clients/{client_id}/addresses", response_model=list[Address])
def addresses(client_id: int, session: Session = Depends(get_session), _: User = Depends(require_roles("admin", "manager"))):
    if not session.get(Client, client_id):
        raise HTTPException(404, "Client not found")
    return session.exec(select(Address).where(Address.client_id == client_id)).all()


@router.get("/clients/{client_id}/orders")
def client_orders(client_id: int, session: Session = Depends(get_session), _: User = Depends(require_roles("admin", "manager"))):
    if not session.get(Client, client_id):
        raise HTTPException(404, "Client not found")
    return session.exec(select(DeliveryOrder).where((DeliveryOrder.sender_client_id == client_id) | (DeliveryOrder.recipient_client_id == client_id)).order_by(DeliveryOrder.created_at.desc())).all()


@router.post("/clients/{client_id}/addresses", response_model=Address, status_code=201)
def create_address(client_id: int, data: AddressInput, session: Session = Depends(get_session), _: User = Depends(require_roles("admin", "manager"))):
    if not session.get(Client, client_id):
        raise HTTPException(404, "Client not found")
    address = Address(client_id=client_id, **data.model_dump())
    session.add(address)
    session.commit()
    session.refresh(address)
    return address


@router.get("/services", response_model=list[DeliveryService])
def services(session: Session = Depends(get_session), _: User = Depends(current_user)):
    return session.exec(select(DeliveryService).where(DeliveryService.is_active == True).order_by(DeliveryService.name)).all()  # noqa: E712


@router.post("/services", response_model=DeliveryService, status_code=201)
def create_service(data: ServiceInput, session: Session = Depends(get_session), _: User = Depends(require_roles("admin", "manager"))):
    if session.exec(select(DeliveryService).where(DeliveryService.code == data.code)).first():
        raise HTTPException(409, "Service code already exists")
    service = DeliveryService(**data.model_dump())
    session.add(service)
    session.commit()
    session.refresh(service)
    return service


@router.patch("/services/{service_id}", response_model=DeliveryService)
def update_service(service_id: int, data: ServiceUpdate, session: Session = Depends(get_session), _: User = Depends(require_roles("admin", "manager"))):
    service = session.get(DeliveryService, service_id)
    if not service:
        raise HTTPException(404, "Service not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(service, key, value)
    session.add(service)
    session.commit()
    session.refresh(service)
    return service


@router.get("/employees", response_model=list[Employee])
def employees(session: Session = Depends(get_session), _: User = Depends(current_user)):
    return session.exec(select(Employee).where(Employee.is_active == True).order_by(Employee.full_name)).all()  # noqa: E712


@router.post("/employees", response_model=Employee, status_code=201)
def create_employee(data: EmployeeInput, session: Session = Depends(get_session), _: User = Depends(require_roles("admin"))):
    if data.user_id and not session.get(User, data.user_id):
        raise HTTPException(400, "User account does not exist")
    if data.user_id and session.exec(select(Employee).where(Employee.user_id == data.user_id)).first():
        raise HTTPException(409, "User already has an employee profile")
    if data.user_id:
        linked_user = session.get(User, data.user_id)
        linked_role = session.get(Role, linked_user.role_id)
        if not linked_role or linked_role.name != "courier":
            raise HTTPException(400, "Employee profile must be linked to a courier account")
    employee = Employee(**data.model_dump())
    session.add(employee)
    session.commit()
    session.refresh(employee)
    return employee


@router.get("/vehicles", response_model=list[Vehicle])
def vehicles(session: Session = Depends(get_session), _: User = Depends(current_user)):
    return session.exec(select(Vehicle).where(Vehicle.is_active == True)).all()  # noqa: E712


@router.post("/vehicles", response_model=Vehicle, status_code=201)
def create_vehicle(data: VehicleInput, session: Session = Depends(get_session), _: User = Depends(require_roles("admin"))):
    if session.exec(select(Vehicle).where(Vehicle.plate_number == data.plate_number)).first():
        raise HTTPException(409, "Vehicle plate number already exists")
    vehicle = Vehicle(**data.model_dump())
    session.add(vehicle)
    session.commit()
    session.refresh(vehicle)
    return vehicle


@router.post("/orders", status_code=201)
def create_order(data: OrderInput, session: Session = Depends(get_session), user: User = Depends(require_roles("admin", "manager"))):
    sender = session.get(Client, data.sender_client_id)
    recipient = session.get(Client, data.recipient_client_id)
    service = session.get(DeliveryService, data.service_id)
    sender_address = session.get(Address, data.sender_address_id)
    recipient_address = session.get(Address, data.recipient_address_id)
    if not sender or not recipient or not service or not sender_address or not recipient_address:
        raise HTTPException(400, "Sender, recipient, addresses and service must exist")
    if sender_address.client_id != sender.id or recipient_address.client_id != recipient.id:
        raise HTTPException(400, "Each address must belong to its selected client")
    total = max(0, service.base_price + service.price_per_km * data.distance_km + data.weight_kg * 100 - data.discount)
    order_data = data.model_dump()
    order_data["scheduled_at"] = data.scheduled_at or (datetime.now(timezone.utc) + timedelta(hours=service.estimated_hours))
    order = DeliveryOrder(order_number=f"DL-{datetime.now():%y%m%d}-{uuid4().hex[:6].upper()}", total_price=round(total, 2), **order_data)
    session.add(order)
    session.commit()
    session.refresh(order)
    session.add(StatusHistory(order_id=order.id, old_status="", new_status="new", changed_by_user_id=user.id, comment="Заказ создан"))
    session.commit()
    return order


@router.get("/orders")
def list_orders(
    q: Optional[str] = None, status_filter: Optional[str] = Query(default=None, alias="status"),
    courier_id: Optional[int] = None, service_id: Optional[int] = None,
    min_price: Optional[float] = Query(default=None, ge=0), max_price: Optional[float] = Query(default=None, ge=0),
    date_from: Optional[datetime] = None, date_to: Optional[datetime] = None,
    offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session), _: User = Depends(current_user),
):
    stmt = select(DeliveryOrder)
    if q:
        sender_ids = select(Client.id).where((Client.full_name.contains(q)) | (Client.phone.contains(q)))
        stmt = stmt.where((DeliveryOrder.order_number.contains(q)) | (DeliveryOrder.sender_client_id.in_(sender_ids)) | (DeliveryOrder.recipient_client_id.in_(sender_ids)))
    if status_filter:
        stmt = stmt.where(DeliveryOrder.status == status_filter)
    if courier_id:
        stmt = stmt.where(DeliveryOrder.courier_id == courier_id)
    if service_id:
        stmt = stmt.where(DeliveryOrder.service_id == service_id)
    if min_price is not None:
        stmt = stmt.where(DeliveryOrder.total_price >= min_price)
    if max_price is not None:
        stmt = stmt.where(DeliveryOrder.total_price <= max_price)
    if date_from:
        stmt = stmt.where(DeliveryOrder.created_at >= date_from)
    if date_to:
        stmt = stmt.where(DeliveryOrder.created_at <= date_to)
    role = session.get(Role, _.role_id)
    if role and role.name == "courier":
        employee = session.exec(select(Employee).where(Employee.user_id == _.id)).first()
        stmt = stmt.where(DeliveryOrder.courier_id == (employee.id if employee else -1))
    return session.exec(stmt.order_by(DeliveryOrder.created_at.desc()).offset(offset).limit(limit)).all()


@router.get("/orders/{order_id}")
def get_order(order_id: int, session: Session = Depends(get_session), _: User = Depends(current_user)):
    order = session.get(DeliveryOrder, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    ensure_order_access(order, _, session)
    return order


@router.get("/orders/{order_id}/history", response_model=list[StatusHistory])
def order_history(order_id: int, session: Session = Depends(get_session), _: User = Depends(current_user)):
    order = session.get(DeliveryOrder, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    ensure_order_access(order, _, session)
    return session.exec(select(StatusHistory).where(StatusHistory.order_id == order_id).order_by(StatusHistory.changed_at)).all()


@router.get("/orders/{order_id}/parcels", response_model=list[Parcel])
def order_parcels(order_id: int, session: Session = Depends(get_session), _: User = Depends(current_user)):
    order = session.get(DeliveryOrder, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    ensure_order_access(order, _, session)
    return session.exec(select(Parcel).where(Parcel.order_id == order_id)).all()


@router.post("/orders/{order_id}/parcels", response_model=Parcel, status_code=201)
def add_parcel(order_id: int, data: ParcelInput, session: Session = Depends(get_session), _: User = Depends(require_roles("admin", "manager"))):
    order = session.get(DeliveryOrder, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    parcel = Parcel(order_id=order.id, **data.model_dump())
    order.weight_kg += parcel.weight_kg
    order.total_price = round(order.total_price + parcel.weight_kg * 100, 2)
    session.add_all([parcel, order])
    session.commit()
    session.refresh(parcel)
    return parcel


@router.post("/orders/{order_id}/assign")
def assign_order(order_id: int, data: AssignInput, session: Session = Depends(get_session), user: User = Depends(require_roles("admin", "manager"))):
    order = session.get(DeliveryOrder, order_id)
    courier = session.get(Employee, data.courier_id)
    if not order or not courier or not courier.is_active:
        raise HTTPException(404, "Order or active courier not found")
    if data.route_id and not session.get(DeliveryRoute, data.route_id):
        raise HTTPException(404, "Route not found")
    if data.route_id:
        route = session.get(DeliveryRoute, data.route_id)
        if route.courier_id and route.courier_id != courier.id:
            raise HTTPException(400, "Route is assigned to another courier")
    for prior in session.exec(select(Assignment).where(Assignment.order_id == order.id, Assignment.active == True)).all():  # noqa: E712
        prior.active = False
        session.add(prior)
    order.courier_id = courier.id
    order.route_id = data.route_id
    session.add(Assignment(order_id=order.id, courier_id=courier.id, assigned_by_user_id=user.id))
    if order.status == "new":
        record_status(session, order, "confirmed", user.id, "Заказ подтвержден перед назначением")
    if order.status == "confirmed":
        record_status(session, order, "assigned", user.id, f"Курьер: {courier.full_name}")
    session.add(order)
    session.commit()
    return order


@router.patch("/orders/{order_id}/status")
def change_status(order_id: int, data: StatusInput, session: Session = Depends(get_session), user: User = Depends(current_user)):
    order = session.get(DeliveryOrder, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    role = session.get(Role, user.role_id)
    employee = session.exec(select(Employee).where(Employee.user_id == user.id)).first() if role and role.name == "courier" else None
    if role and role.name == "courier" and (not employee or order.courier_id != employee.id):
        raise HTTPException(403, "Courier can update only assigned orders")
    if role and role.name not in {"admin", "manager", "courier"}:
        raise HTTPException(403, "Insufficient role")
    record_status(session, order, data.status, user.id, data.comment)
    if data.status == "delivered" and order.route_id:
        for stop in session.exec(select(RouteStop).where(RouteStop.order_id == order.id, RouteStop.route_id == order.route_id)).all():
            stop.completed_at = datetime.now(timezone.utc)
            session.add(stop)
    if data.status == "delivered":
        paid = sum(p.amount for p in session.exec(select(Payment).where(Payment.order_id == order.id, Payment.status == "paid")).all())
        if paid >= order.total_price:
            record_status(session, order, "paid", user.id, "Ранее принятая оплата подтверждена")
    session.add(order)
    session.commit()
    return order


@router.post("/orders/{order_id}/payments", response_model=Payment, status_code=201)
def pay_order(order_id: int, data: PaymentInput, session: Session = Depends(get_session), user: User = Depends(require_roles("admin", "manager"))):
    order = session.get(DeliveryOrder, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    paid = sum(p.amount for p in session.exec(select(Payment).where(Payment.order_id == order.id, Payment.status == "paid")).all())
    if paid + data.amount > order.total_price + 0.001:
        raise HTTPException(400, "Payment exceeds order balance")
    payment = Payment(order_id=order.id, **data.model_dump())
    session.add(payment)
    if paid + data.amount >= order.total_price and order.status == "delivered":
        record_status(session, order, "paid", user.id, "Оплата получена")
    session.add(order)
    session.commit()
    session.refresh(payment)
    return payment


@router.post("/orders/{order_id}/reviews", response_model=Review, status_code=201)
def review_order(order_id: int, data: ReviewInput, session: Session = Depends(get_session), user: User = Depends(current_user)):
    order = session.get(DeliveryOrder, order_id)
    if not order or order.status not in {"delivered", "paid", "closed"}:
        raise HTTPException(400, "Only delivered orders can be reviewed")
    if session.exec(select(Review).where(Review.order_id == order.id)).first():
        raise HTTPException(409, "This order already has a review")
    review = Review(order_id=order.id, client_id=order.sender_client_id, **data.model_dump())
    session.add(review)
    session.commit()
    session.refresh(review)
    return review


@router.post("/routes", response_model=DeliveryRoute, status_code=201)
def create_route(data: RouteInput, session: Session = Depends(get_session), _: User = Depends(require_roles("admin", "manager"))):
    if session.exec(select(DeliveryRoute).where(DeliveryRoute.code == data.code)).first():
        raise HTTPException(409, "Route code already exists")
    route = DeliveryRoute(**data.model_dump())
    session.add(route)
    session.commit()
    session.refresh(route)
    return route


@router.get("/routes", response_model=list[DeliveryRoute])
def routes(session: Session = Depends(get_session), _: User = Depends(require_roles("admin", "manager"))):
    return session.exec(select(DeliveryRoute).order_by(DeliveryRoute.planned_date.desc())).all()


@router.get("/routes/{route_id}/stops", response_model=list[RouteStop])
def route_stops(route_id: int, session: Session = Depends(get_session), _: User = Depends(require_roles("admin", "manager"))):
    if not session.get(DeliveryRoute, route_id):
        raise HTTPException(404, "Route not found")
    return session.exec(select(RouteStop).where(RouteStop.route_id == route_id).order_by(RouteStop.sequence)).all()


@router.post("/routes/{route_id}/stops", response_model=RouteStop, status_code=201)
def add_route_stop(route_id: int, data: RouteStopInput, session: Session = Depends(get_session), _: User = Depends(require_roles("admin", "manager"))):
    route, order = session.get(DeliveryRoute, route_id), session.get(DeliveryOrder, data.order_id)
    if not route or not order:
        raise HTTPException(404, "Route or order not found")
    if route.courier_id and order.courier_id and route.courier_id != order.courier_id:
        raise HTTPException(400, "Route and order must be assigned to the same courier")
    stop = RouteStop(route_id=route.id, **data.model_dump())
    order.route_id = route.id
    session.add(stop)
    session.add(order)
    session.commit()
    session.refresh(stop)
    return stop


@router.get("/reports/summary")
def report_summary(session: Session = Depends(get_session), _: User = Depends(require_roles("admin", "manager"))):
    orders = session.exec(select(DeliveryOrder)).all()
    paid = session.exec(select(Payment).where(Payment.status == "paid")).all()
    def is_overdue(order):
        due = order.scheduled_at
        if due is None:
            return False
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        return due < datetime.now(timezone.utc) and order.status not in {"delivered", "paid", "closed", "cancelled"}
    return {"total_orders": len(orders), "new": sum(o.status == "new" for o in orders),
            "in_progress": sum(o.status in {"confirmed", "assigned", "in_transit", "delayed"} for o in orders),
            "delivered": sum(o.status in {"delivered", "paid", "closed"} for o in orders),
            "overdue": sum(is_overdue(o) for o in orders),
            "revenue": round(sum(p.amount for p in paid), 2)}


@router.get("/reports/orders-by-month")
def report_orders_by_month(session: Session = Depends(get_session), _: User = Depends(require_roles("admin", "manager"))):
    counts = {}
    for order in session.exec(select(DeliveryOrder)).all():
        key = order.created_at.strftime("%Y-%m")
        counts[key] = counts.get(key, 0) + 1
    return [{"month": key, "orders": value} for key, value in sorted(counts.items())]


@router.get("/reports/by-service")
def report_by_service(session: Session = Depends(get_session), _: User = Depends(require_roles("admin", "manager"))):
    services = {s.id: s.name for s in session.exec(select(DeliveryService)).all()}
    report = {}
    for order in session.exec(select(DeliveryOrder)).all():
        item = report.setdefault(order.service_id, {"service": services.get(order.service_id, ""), "orders": 0, "revenue": 0.0})
        item["orders"] += 1
        item["revenue"] += order.total_price
    return sorted(report.values(), key=lambda x: x["orders"], reverse=True)


@router.get("/reports/by-courier")
def report_by_courier(session: Session = Depends(get_session), _: User = Depends(require_roles("admin", "manager"))):
    couriers = {e.id: e.full_name for e in session.exec(select(Employee)).all()}
    report = {}
    for order in session.exec(select(DeliveryOrder).where(DeliveryOrder.courier_id != None)).all():  # noqa: E711
        item = report.setdefault(order.courier_id, {"courier": couriers.get(order.courier_id, ""), "orders": 0, "delivered": 0})
        item["orders"] += 1
        item["delivered"] += int(order.status in {"delivered", "paid", "closed"})
    return sorted(report.values(), key=lambda x: x["orders"], reverse=True)


@router.get("/reports/popular-services")
def report_popular_services(session: Session = Depends(get_session), _: User = Depends(require_roles("admin", "manager"))):
    return report_by_service(session, _)


@router.get("/reports/top-clients")
def report_top_clients(session: Session = Depends(get_session), _: User = Depends(require_roles("admin", "manager"))):
    names = {c.id: c.full_name for c in session.exec(select(Client)).all()}
    counts = {}
    for order in session.exec(select(DeliveryOrder)).all():
        counts[order.sender_client_id] = counts.get(order.sender_client_id, 0) + 1
    return sorted([{"client": names.get(k, ""), "orders": v} for k, v in counts.items()], key=lambda x: x["orders"], reverse=True)


@router.get("/reports/overdue")
def report_overdue(session: Session = Depends(get_session), _: User = Depends(require_roles("admin", "manager"))):
    now = datetime.now(timezone.utc)
    orders = session.exec(select(DeliveryOrder)).all()
    def overdue(order):
        due = order.scheduled_at
        if not due:
            return False
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        return due < now and order.status not in {"delivered", "paid", "closed", "cancelled"}
    return [o for o in orders if overdue(o)]
