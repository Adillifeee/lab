from datetime import datetime, timezone

from sqlalchemy import inspect
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.database.models import (
    Address,
    Assignment,
    Client,
    DeliveryOrder,
    DeliveryRoute,
    DeliveryService,
    Employee,
    Parcel,
    Payment,
    Review,
    Role,
    RouteStop,
    StatusHistory,
    User,
    Vehicle,
)


def test_schema_and_orm_relationships():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    assert set(inspect(engine).get_table_names()) == set(SQLModel.metadata.tables)

    role = Role(name="manager")
    user = User(username="manager", password_hash="hash", role=role)
    employee = Employee(full_name="Courier", phone="123", user=user)
    sender = Client(full_name="Sender", phone="111")
    recipient = Client(full_name="Recipient", phone="222")
    sender_address = Address(client=sender, city="Almaty", street="Abay", building="1")
    recipient_address = Address(client=recipient, city="Almaty", street="Dostyk", building="2")
    service = DeliveryService(code="STD", name="Standard", base_price=100)
    vehicle = Vehicle(plate_number="KZ-101", capacity_kg=100)
    route = DeliveryRoute(
        code="R-1",
        name="Route",
        planned_date=datetime.now(timezone.utc),
        courier=employee,
        vehicle=vehicle,
    )
    order = DeliveryOrder(
        order_number="DL-1",
        sender=sender,
        recipient=recipient,
        sender_address=sender_address,
        recipient_address=recipient_address,
        service=service,
        route=route,
        courier=employee,
    )
    stop = RouteStop(route=route, order=order, sequence=1)
    parcel = Parcel(order=order, description="Documents")
    assignment = Assignment(order=order, courier=employee, assigned_by=user)
    history = StatusHistory(order=order, new_status="new", changed_by=user)
    payment = Payment(order=order, amount=100)
    review = Review(order=order, client=sender, rating=5)

    with Session(engine) as session:
        session.add_all([
            role,
            user,
            employee,
            sender,
            recipient,
            sender_address,
            recipient_address,
            service,
            vehicle,
            route,
            order,
            stop,
            parcel,
            assignment,
            history,
            payment,
            review,
        ])
        session.commit()

        assert role.users[0].employee is employee
        assert sender.addresses[0].client is sender
        assert sender.sent_orders[0].recipient is recipient
        assert recipient.received_orders[0].sender is sender
        assert sender_address.sender_orders[0] is order
        assert recipient_address.recipient_orders[0] is order
        assert service.orders[0] is order
        assert vehicle.routes[0] is route
        assert route.orders[0] is order
        assert route.stops[0].order is order
        assert order.route_stops[0] is stop
        assert order.parcels[0] is parcel
        assert employee.delivery_orders[0] is order
        assert employee.assignments[0] is assignment
        assert user.assignments_made[0] is assignment
        assert order.status_history[0].changed_by is user
        assert order.payments[0] is payment
        assert order.review.client is sender

    engine.dispose()
