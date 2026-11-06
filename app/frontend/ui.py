import os

import pandas as pd
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")
st.set_page_config(page_title="Городская доставка", page_icon="🚚", layout="wide")
st.title("🚚 АРМ службы доставки товаров по городу")
st.caption("Заказы · адреса · курьеры · маршруты · оплата · отчеты")


def request(method: str, path: str, **kwargs):
    headers = kwargs.pop("headers", {})
    if st.session_state.get("token"):
        headers["Authorization"] = f'Bearer {st.session_state.token}'
    try:
        response = requests.request(method, f"{API_URL}{path}", headers=headers, timeout=10, **kwargs)
        if response.status_code >= 400:
            try:
                st.error(response.json().get("detail", "Ошибка запроса"))
            except ValueError:
                st.error(response.text or f"HTTP {response.status_code}")
            return None
        return response.json() if response.content else True
    except requests.RequestException as exc:
        st.error(f"API недоступен: {exc}")
        return None


if not st.session_state.get("token"):
    st.subheader("Вход в систему")
    with st.form("login"):
        username = st.text_input("Логин")
        password = st.text_input("Пароль", type="password")
        submit = st.form_submit_button("Войти", type="primary")
    if submit:
        try:
            response = requests.post(f"{API_URL}/auth/login", json={"username": username, "password": password}, timeout=10)
            if response.status_code == 200:
                st.session_state.token = response.json()["access_token"]
                st.session_state.username = username
                st.rerun()
            st.error("Неверный логин или пароль")
        except requests.RequestException as exc:
            st.error(f"API недоступен: {exc}")
    st.info("Демо: admin / Admin123! · manager / Manager123! · courier1 / Courier1!")
    st.stop()

profile = request("GET", "/auth/me")
if not profile:
    st.session_state.clear()
    st.rerun()
with st.sidebar:
    st.write(f'**{profile["username"]}** · {profile["role"]}')
    if st.button("Выйти"):
        st.session_state.clear()
        st.rerun()

role = profile["role"]
if role == "courier":
    pages = ["Мои доставки"]
else:
    pages = ["Главная", "Заказы", "Клиенты", "Услуги", "Маршруты", "Отчеты"]
    if role == "admin":
        pages.append("Пользователи")
page = st.sidebar.radio("Раздел", pages)

STATUS_LABELS = {
    "new": "Новый", "confirmed": "Подтвержден", "assigned": "Назначен курьер",
    "in_transit": "В пути", "delayed": "Задержан", "delivered": "Доставлен",
    "paid": "Оплачен", "closed": "Закрыт", "cancelled": "Отменен",
}

if page == "Главная":
    metrics = request("GET", "/reports/summary") or {}
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Всего заказов", metrics.get("total_orders", 0))
    c2.metric("Новые", metrics.get("new", 0))
    c3.metric("В работе", metrics.get("in_progress", 0))
    c4.metric("Просрочены", metrics.get("overdue", 0))
    c5.metric("Выручка", f'{metrics.get("revenue", 0):,.0f} ₸')
    st.subheader("Последние заказы")
    orders = request("GET", "/orders", params={"limit": 10}) or []
    if orders:
        st.dataframe(pd.DataFrame([{"Номер": o["order_number"], "Статус": STATUS_LABELS.get(o["status"], o["status"]), "Стоимость": o["total_price"], "Создан": o["created_at"]} for o in orders]), use_container_width=True, hide_index=True)

elif page in {"Заказы", "Мои доставки"}:
    st.subheader("Заказы доставки")
    if role != "courier":
        with st.expander("Создать заказ"):
            clients = request("GET", "/clients") or []
            services = request("GET", "/services") or []
            if len(clients) < 2 or not services:
                st.info("Для создания заказа нужны минимум два клиента и одна услуга.")
            else:
                client_labels = {f'{c["full_name"]} · {c["phone"]}': c for c in clients}
                with st.form("create_order"):
                    sender_label = st.selectbox("Отправитель", list(client_labels))
                    recipient_labels = [label for label in client_labels if label != sender_label]
                    recipient_label = st.selectbox("Получатель", recipient_labels)
                    sender = client_labels[sender_label]
                    recipient = client_labels[recipient_label]
                    sender_addresses = request("GET", f'/clients/{sender["id"]}/addresses') or []
                    recipient_addresses = request("GET", f'/clients/{recipient["id"]}/addresses') or []
                    create = False
                    if not sender_addresses or not recipient_addresses:
                        st.warning("Добавьте адреса отправителя и получателя в разделе «Клиенты».")
                    else:
                        sa = st.selectbox("Адрес отправления", sender_addresses, format_func=lambda a: f'{a["city"]}, {a["street"]}, {a["building"]}')
                        ra = st.selectbox("Адрес доставки", recipient_addresses, format_func=lambda a: f'{a["city"]}, {a["street"]}, {a["building"]}')
                        service = st.selectbox("Услуга", services, format_func=lambda s: f'{s["name"]} · от {s["base_price"]} ₸')
                        distance = st.number_input("Расстояние, км", min_value=0.0, step=1.0)
                        weight = st.number_input("Вес, кг", min_value=0.0, step=0.5)
                        description = st.text_input("Описание отправления")
                        create = st.form_submit_button("Зарегистрировать заказ", type="primary")
                    if create:
                        result = request("POST", "/orders", json={"sender_client_id": sender["id"], "recipient_client_id": recipient["id"], "sender_address_id": sa["id"], "recipient_address_id": ra["id"], "service_id": service["id"], "distance_km": distance, "weight_kg": weight, "description": description})
                        if result:
                            st.success(f'Заказ {result["order_number"]} создан. Стоимость: {result["total_price"]} ₸')
                            st.rerun()
    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    search = col1.text_input("Номер заказа, клиент или телефон")
    status_values = ["Все статусы", *STATUS_LABELS.keys()]
    selected_status = col2.selectbox("Статус", status_values)
    couriers = request("GET", "/employees") or []
    courier_options = {"Все курьеры": None, **{e["full_name"]: e["id"] for e in couriers}}
    selected_courier = col3.selectbox("Курьер", list(courier_options))
    services = request("GET", "/services") or []
    service_options = {"Все услуги": None, **{s["name"]: s["id"] for s in services}}
    selected_service = col4.selectbox("Услуга", list(service_options))
    params = {"limit": 200}
    if search:
        params["q"] = search
    if selected_status != "Все статусы":
        params["status"] = selected_status
    if courier_options[selected_courier]:
        params["courier_id"] = courier_options[selected_courier]
    if service_options[selected_service]:
        params["service_id"] = service_options[selected_service]
    p1, p2, p3, p4 = st.columns(4)
    min_price = p1.number_input("Цена от, ₸", min_value=0.0, step=500.0, key="filter_min_price")
    max_price = p2.number_input("Цена до, ₸ (0 — без лимита)", min_value=0.0, step=500.0, key="filter_max_price")
    filter_dates = p3.checkbox("Фильтровать по дате")
    if min_price:
        params["min_price"] = min_price
    if max_price:
        params["max_price"] = max_price
    if filter_dates:
        date_from = p3.date_input("Создан после", key="filter_date_from")
        date_to = p4.date_input("Создан до", key="filter_date_to")
        params["date_from"] = f"{date_from.isoformat()}T00:00:00"
        params["date_to"] = f"{date_to.isoformat()}T23:59:59"
    orders = request("GET", "/orders", params=params) or []
    if orders:
        st.dataframe(pd.DataFrame([{"ID": o["id"], "Номер": o["order_number"], "Статус": STATUS_LABELS.get(o["status"], o["status"]), "Курьер ID": o["courier_id"], "Стоимость, ₸": o["total_price"], "Создан": o["created_at"]} for o in orders]), use_container_width=True, hide_index=True)
        selected = st.selectbox("Выберите заказ для операции", orders, format_func=lambda o: f'{o["order_number"]} · {STATUS_LABELS.get(o["status"], o["status"])}')
        if role != "courier":
            left, right = st.columns(2)
            with left:
                with st.form("assign"):
                    courier = st.selectbox("Назначить курьера", couriers, format_func=lambda e: e["full_name"])
                    if st.form_submit_button("Назначить"):
                        result = request("POST", f'/orders/{selected["id"]}/assign', json={"courier_id": courier["id"]})
                        if result:
                            st.success("Курьер назначен")
                            st.rerun()
            with right:
                with st.form("pay"):
                    amount = st.number_input("Сумма оплаты, ₸", min_value=0.01, value=max(0.01, float(selected["total_price"])), step=100.0)
                    method = st.selectbox("Способ оплаты", ["cash", "card", "transfer"])
                    if st.form_submit_button("Принять оплату"):
                        result = request("POST", f'/orders/{selected["id"]}/payments', json={"amount": amount, "method": method})
                        if result:
                            st.success("Оплата зарегистрирована")
                            st.rerun()
        with st.form("status"):
            allowed = [s for s in STATUS_LABELS if s != selected["status"]]
            new_status = st.selectbox("Новый статус", allowed, format_func=lambda s: STATUS_LABELS[s])
            comment = st.text_input("Комментарий к изменению")
            if st.form_submit_button("Обновить статус"):
                result = request("PATCH", f'/orders/{selected["id"]}/status', json={"status": new_status, "comment": comment})
                if result:
                    st.success("Статус обновлен")
                    st.rerun()
        with st.expander("История статусов"):
            history = request("GET", f'/orders/{selected["id"]}/history') or []
            if history:
                st.dataframe(pd.DataFrame([{"Дата": h["changed_at"], "Было": h["old_status"], "Стало": h["new_status"], "Комментарий": h["comment"]} for h in history]), use_container_width=True, hide_index=True)
        if role != "courier":
            with st.expander("Добавить посылку к заказу"):
                with st.form("new_parcel"):
                    parcel_description = st.text_input("Описание посылки")
                    parcel_weight = st.number_input("Вес посылки, кг", min_value=0.0, step=0.5)
                    length = st.number_input("Длина, см", min_value=0.0, step=1.0)
                    width = st.number_input("Ширина, см", min_value=0.0, step=1.0)
                    height = st.number_input("Высота, см", min_value=0.0, step=1.0)
                    if st.form_submit_button("Добавить посылку") and parcel_description:
                        result = request("POST", f'/orders/{selected["id"]}/parcels', json={"description": parcel_description, "weight_kg": parcel_weight, "length_cm": length, "width_cm": width, "height_cm": height})
                        if result:
                            st.success("Посылка добавлена")
                            st.rerun()
    else:
        st.info("Заказы по выбранным условиям не найдены.")

elif page == "Клиенты":
    st.subheader("Клиенты и адреса")
    with st.form("new_client"):
        fullname = st.text_input("ФИО клиента")
        phone = st.text_input("Телефон")
        email = st.text_input("Электронная почта")
        submitted = st.form_submit_button("Добавить клиента")
    if submitted and fullname and phone:
        result = request("POST", "/clients", json={"full_name": fullname, "phone": phone, "email": email})
        if result:
            st.success(f'Клиент {result["full_name"]} добавлен')
            st.rerun()
    query = st.text_input("Поиск клиента по имени или телефону")
    clients = request("GET", "/clients", params={"q": query} if query else {}) or []
    if clients:
        st.dataframe(pd.DataFrame(clients)[["id", "full_name", "phone", "email"]], use_container_width=True, hide_index=True)
        client = st.selectbox("Клиент для нового адреса", clients, format_func=lambda c: f'{c["full_name"]} · {c["phone"]}')
        with st.form("new_address"):
            label = st.text_input("Метка", value="Дом")
            city = st.text_input("Город", value="Алматы")
            street = st.text_input("Улица")
            building = st.text_input("Дом")
            apartment = st.text_input("Квартира / офис")
            if st.form_submit_button("Добавить адрес") and street and building:
                result = request("POST", f'/clients/{client["id"]}/addresses', json={"label": label, "city": city, "street": street, "building": building, "apartment": apartment})
                if result:
                    st.success("Адрес добавлен")
                    st.rerun()
        st.subheader("История заказов клиента")
        client_orders = request("GET", f'/clients/{client["id"]}/orders') or []
        if client_orders:
            st.dataframe(pd.DataFrame([{"Номер": o["order_number"], "Статус": STATUS_LABELS.get(o["status"], o["status"]), "Стоимость": o["total_price"]} for o in client_orders]), use_container_width=True, hide_index=True)

elif page == "Услуги":
    st.subheader("Каталог тарифных услуг")
    services = request("GET", "/services") or []
    if services:
        st.dataframe(pd.DataFrame(services)[["id", "code", "name", "base_price", "price_per_km", "estimated_hours"]], use_container_width=True, hide_index=True)
    with st.expander("Добавить услугу"):
        with st.form("new_service"):
            code = st.text_input("Код")
            name = st.text_input("Название")
            description = st.text_input("Описание")
            base = st.number_input("Базовая стоимость, ₸", min_value=0.0, step=100.0)
            per_km = st.number_input("Стоимость за км, ₸", min_value=0.0, step=10.0)
            hours = st.number_input("Срок, часов", min_value=1, value=24)
            if st.form_submit_button("Сохранить услугу") and code and name:
                result = request("POST", "/services", json={"code": code, "name": name, "description": description, "base_price": base, "price_per_km": per_km, "estimated_hours": hours})
                if result:
                    st.success("Услуга добавлена")
                    st.rerun()
    if services:
        with st.expander("Изменить стоимость услуги"):
            service = st.selectbox("Услуга", services, format_func=lambda s: s["name"])
            new_price = st.number_input("Новая базовая стоимость, ₸", min_value=0.0, value=float(service["base_price"]), step=100.0)
            if st.button("Обновить тариф"):
                result = request("PATCH", f'/services/{service["id"]}', json={"base_price": new_price})
                if result:
                    st.success("Тариф обновлен")
                    st.rerun()

elif page == "Маршруты":
    st.subheader("Маршруты курьеров")
    routes = request("GET", "/routes") or []
    couriers = request("GET", "/employees") or []
    vehicles = request("GET", "/vehicles") or []
    if routes:
        st.dataframe(pd.DataFrame(routes)[["id", "code", "name", "planned_date", "courier_id", "vehicle_id", "status"]], use_container_width=True, hide_index=True)
        selected_route = st.selectbox("Маршрут для просмотра остановок", routes, format_func=lambda r: f'{r["code"]} · {r["name"]}')
        stops = request("GET", f'/routes/{selected_route["id"]}/stops') or []
        if stops:
            st.dataframe(pd.DataFrame(stops)[["sequence", "order_id", "completed_at"]], use_container_width=True, hide_index=True)
        open_orders = request("GET", "/orders", params={"status": "assigned", "limit": 200}) or []
        if open_orders:
            with st.form("route_stop"):
                route_order = st.selectbox("Добавить заказ в маршрут", open_orders, format_func=lambda o: o["order_number"])
                sequence = st.number_input("Порядок остановки", min_value=1, step=1, value=len(stops) + 1)
                if st.form_submit_button("Добавить остановку"):
                    result = request("POST", f'/routes/{selected_route["id"]}/stops', json={"order_id": route_order["id"], "sequence": sequence})
                    if result:
                        st.success("Остановка добавлена")
                        st.rerun()
    with st.expander("Создать маршрут"):
        with st.form("new_route"):
            code = st.text_input("Код маршрута")
            name = st.text_input("Название")
            courier = st.selectbox("Курьер", couriers, format_func=lambda e: e["full_name"])
            vehicle = st.selectbox("Транспорт", vehicles, format_func=lambda v: f'{v["vehicle_type"]} · {v["plate_number"]}')
            planned = st.date_input("Дата")
            if st.form_submit_button("Создать маршрут") and code:
                result = request("POST", "/routes", json={"code": code, "name": name, "courier_id": courier["id"], "vehicle_id": vehicle["id"], "planned_date": f"{planned.isoformat()}T09:00:00Z"})
                if result:
                    st.success("Маршрут создан")
                    st.rerun()

elif page == "Отчеты":
    st.subheader("Операционная отчетность")
    report = st.selectbox("Отчет", ["Заказы по месяцам", "Выручка и популярность услуг", "Нагрузка курьеров", "Постоянные клиенты", "Просроченные заказы"])
    paths = {"Заказы по месяцам": "/reports/orders-by-month", "Выручка и популярность услуг": "/reports/by-service", "Нагрузка курьеров": "/reports/by-courier", "Постоянные клиенты": "/reports/top-clients", "Просроченные заказы": "/reports/overdue"}
    rows = request("GET", paths[report]) or []
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("Для этого отчета пока нет данных.")

elif page == "Пользователи":
    st.subheader("Учетные записи и роли")
    users = request("GET", "/users") or []
    if users:
        st.dataframe(pd.DataFrame(users), use_container_width=True, hide_index=True)
    roles = request("GET", "/roles") or []
    if roles:
        with st.form("new_user"):
            username = st.text_input("Логин нового пользователя")
            password = st.text_input("Пароль (не менее 8 знаков)", type="password")
            role_name = st.selectbox("Роль", [r["name"] for r in roles])
            if st.form_submit_button("Создать пользователя") and username and password:
                result = request("POST", "/users", json={"username": username, "password": password, "role": role_name})
                if result:
                    st.success("Пользователь создан")
                    st.rerun()
        couriers = [u for u in users if u["role"] == "courier"]
        with st.expander("Добавить карточку сотрудника / курьера"):
            with st.form("new_employee"):
                employee_name = st.text_input("ФИО сотрудника")
                employee_phone = st.text_input("Телефон сотрудника")
                linked_account = st.selectbox("Учетная запись курьера", [None, *couriers], format_func=lambda u: "Без учетной записи" if u is None else u["username"])
                if st.form_submit_button("Создать карточку") and employee_name and employee_phone:
                    result = request("POST", "/employees", json={"full_name": employee_name, "phone": employee_phone, "position": "Курьер", "user_id": linked_account["id"] if linked_account else None})
                    if result:
                        st.success("Карточка сотрудника создана")
                        st.rerun()
