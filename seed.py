"""Idempotent demo dataset for variant 13 (urban delivery service)."""
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.database.db import create_db_and_tables, engine
from app.database.models import (
    Address, Assignment, Client, DeliveryOrder, DeliveryRoute, DeliveryService,
    Employee, Payment, Role, RouteStop, StatusHistory, User, Vehicle,
)
from app.security import hash_password

CLIENT_NAMES = [
    "Айдана Сәрсенова", "Нұржан Әлиев", "Дана Мұратова", "Ерлан Қасымов", "Алия Омарова",
    "Арман Беков", "Жанар Нұрланова", "Мирас Төлегенов", "Мадина Сапарова", "Данияр Жұмабеков",
    "Әсел Қуанышбаева", "Руслан Иманов", "Салтанат Ермекова", "Бауыржан Ахметов", "Аружан Кәрімова",
    "Тимур Жақыпов", "Камила Нұрбекова", "Әділхан Сейітов", "Назерке Досанова", "Мақсат Рахимов",
]
SERVICE_DATA = [
    ("STD", "Стандартная доставка", 900, 80, 24), ("EXP", "Экспресс-доставка", 1600, 120, 4),
    ("SAME", "Доставка день в день", 1300, 100, 10), ("DOC", "Доставка документов", 700, 60, 12),
    ("FRAG", "Хрупкий груз", 1800, 150, 24), ("FOOD", "Доставка продуктов", 1100, 90, 6),
    ("NIGHT", "Вечерняя доставка", 1400, 110, 8), ("BULK", "Крупногабаритная доставка", 2400, 180, 36),
    ("PICK", "Забор отправления", 500, 50, 8), ("LOCK", "Доставка до постамата", 800, 70, 24),
]


def seed() -> None:
    create_db_and_tables()
    with Session(engine) as session:
        roles = [Role(name="admin", description="Полный доступ"), Role(name="manager", description="Заказы, клиенты, отчеты"), Role(name="courier", description="Назначенные доставки")]
        for role in roles:
            if not session.exec(select(Role).where(Role.name == role.name)).first():
                session.add(role)
        session.commit()
        role_map = {r.name: r for r in session.exec(select(Role)).all()}
        demo_accounts = [
            ("admin", "Admin123!", "admin"),
            ("manager", "Manager123!", "manager"),
        ]
        demo_accounts.extend((f"courier{i+1}", f"Courier{i+1}!", "courier") for i in range(5))
        for username, password, role_name in demo_accounts:
            if not session.exec(select(User).where(User.username == username)).first():
                session.add(User(username=username, password_hash=hash_password(password), role_id=role_map[role_name].id))
        session.commit()
        accounts = [session.exec(select(User).where(User.username == name)).first() for name in ("admin", "manager")]
        users = [session.exec(select(User).where(User.username == f"courier{i+1}")).first() for i in range(5)]
        if session.exec(select(Client)).first():
            print("Demo roles and accounts are ready; existing demo data was left unchanged.")
            print("Demo login: admin / Admin123! (also manager / Manager123!, courier1 / Courier1!).")
            return
        employees = [Employee(full_name=f"Курьер {i+1}", phone=f"+7 701 555 {i:02d} {i+10:02d}", position="Курьер", user_id=users[i].id) for i in range(5)]
        session.add_all(employees)
        vehicles = [Vehicle(plate_number=f"KZ-{i+101}-DEL", vehicle_type=("Автомобиль" if i < 2 else "Велосипед"), capacity_kg=(300 if i < 2 else 25)) for i in range(5)]
        session.add_all(vehicles)
        session.add_all([DeliveryService(code=d[0], name=d[1], base_price=d[2], price_per_km=d[3], estimated_hours=d[4], description="Городская курьерская услуга") for d in SERVICE_DATA])
        clients = [Client(full_name=n, phone=f"+7 777 100 {i:02d} {i+10:02d}", email=f"client{i+1}@example.kz") for i, n in enumerate(CLIENT_NAMES)]
        session.add_all(clients)
        session.commit()
        addresses = []
        for i, client in enumerate(clients):
            addresses.extend([
                Address(client_id=client.id, label="Дом", city="Алматы", street=f"улица Абая, {i+1}", building=f"{i+1}"),
                Address(client_id=client.id, label="Работа", city="Алматы", street=f"проспект Достык, {i+10}", building=f"{i+10}", apartment="офис 4"),
            ])
        session.add_all(addresses)
        session.commit()
        services = session.exec(select(DeliveryService).order_by(DeliveryService.id)).all()
        routes = [DeliveryRoute(code=f"R-ALM-{i+1:03d}", name=f"Городской маршрут {i+1}", planned_date=datetime.now(timezone.utc) + timedelta(days=1), courier_id=employees[i].id, vehicle_id=vehicles[i].id) for i in range(5)]
        session.add_all(routes)
        session.commit()
        status_paths = {
            "new": [], "confirmed": ["confirmed"], "assigned": ["confirmed", "assigned"],
            "in_transit": ["confirmed", "assigned", "in_transit"],
            "delayed": ["confirmed", "assigned", "in_transit", "delayed"],
            "delivered": ["confirmed", "assigned", "in_transit", "delivered"],
            "paid": ["confirmed", "assigned", "in_transit", "delivered", "paid"],
            "closed": ["confirmed", "assigned", "in_transit", "delivered", "paid", "closed"],
        }
        statuses = list(status_paths)
        for i in range(30):
            sender_index = i % 20
            recipient_index = (i + 7) % 20
            status = statuses[i % len(statuses)]
            created = datetime.now(timezone.utc) - timedelta(days=i % 20, hours=i % 12)
            courier = employees[i % 5] if i % 3 else None
            order = DeliveryOrder(
                order_number=f"DL-DEMO-{i+1:04d}", sender_client_id=clients[sender_index].id,
                recipient_client_id=clients[recipient_index].id, sender_address_id=addresses[sender_index*2].id,
                recipient_address_id=addresses[recipient_index*2].id, service_id=services[i % 10].id,
                route_id=routes[i % 5].id if courier else None, courier_id=courier.id if courier else None,
                status=status, distance_km=2 + i % 15, weight_kg=0.5 + i % 10,
                description="Демонстрационное отправление", declared_value=5000 + i * 250,
                total_price=round(services[i % 10].base_price + services[i % 10].price_per_km * (2 + i % 15) + (0.5 + i % 10) * 100, 2),
                created_at=created, scheduled_at=created + timedelta(hours=services[i % 10].estimated_hours),
                delivered_at=created + timedelta(hours=services[i % 10].estimated_hours - 1) if status in {"delivered", "paid", "closed"} else None,
            )
            session.add(order)
            session.commit()
            session.refresh(order)
            history = [StatusHistory(order_id=order.id, old_status="", new_status="new", changed_by_user_id=accounts[1].id, changed_at=created, comment="Демонстрационный заказ")]
            old = "new"
            for step, new in enumerate(status_paths[status], 1):
                history.append(StatusHistory(order_id=order.id, old_status=old, new_status=new, changed_by_user_id=accounts[1].id, changed_at=created + timedelta(minutes=step * 10), comment="Демонстрационные данные"))
                old = new
            session.add_all(history)
            if courier:
                session.add(Assignment(order_id=order.id, courier_id=courier.id, assigned_by_user_id=accounts[1].id, assigned_at=created + timedelta(minutes=10)))
            if status in {"paid", "closed"}:
                session.add(Payment(order_id=order.id, amount=order.total_price, method="card", status="paid", paid_at=created + timedelta(hours=3)))
            if courier and i % 3:
                session.add(RouteStop(route_id=routes[i % 5].id, order_id=order.id, sequence=i // 5 + 1))
            session.commit()
        print("Seeded 20 clients, 10 services, 5 couriers, 5 vehicles and 30 delivery orders.")
        print("Demo login: admin / Admin123! (also manager / Manager123!, courier1 / Courier1!).")


if __name__ == "__main__":
    seed()
