from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from logistics.models import (
    Client,
    Driver,
    RequestStatus,
    Transportation,
    TransportationRequest,
    Vehicle,
    ensure_default_statuses,
    refresh_all_resource_availability,
)


class Command(BaseCommand):
    help = "Создает или обновляет демоданные для системы управления грузоперевозками."

    def handle(self, *args, **options):
        with transaction.atomic():
            ensure_default_statuses()

            admin_user = self._ensure_admin()
            clients = self._seed_clients()
            statuses = {status.code: status for status in RequestStatus.objects.all()}
            self._reset_demo_requests(clients)
            drivers = self._seed_drivers()
            vehicles = self._seed_vehicles()

            for spec in self._build_request_specs():
                request_obj = self._upsert_request(spec, clients, statuses, admin_user)
                self._upsert_transportation(spec, request_obj, drivers, vehicles, statuses, admin_user)
                self._apply_final_status(spec, request_obj, statuses, admin_user)

            refresh_all_resource_availability()

        self.stdout.write(self.style.SUCCESS("Демоданные успешно созданы."))

    def _build_request_specs(self):
        now = timezone.now()
        today = timezone.localdate()
        sand = TransportationRequest.CargoType.SAND
        crushed_stone = TransportationRequest.CargoType.CRUSHED_STONE
        concrete = TransportationRequest.CargoType.CONCRETE
        return [
            {
                "client": "ООО СтройТранс",
                "cargo_type": concrete,
                "cargo_name": "Бетон М350 для монолитных работ",
                "cargo_weight": 18.5,
                "cargo_volume": None,
                "route_from": "Москва, ул. Промышленная, 12",
                "route_to": "Химки, строительная площадка Северная",
                "transportation_date": today + timedelta(days=1),
                "cost": None,
                "comment": "Разгрузка краном заказчика до 14:00.",
                "status": "assigned",
                "transportation": {
                    "driver": "Иванов Иван Иванович",
                    "vehicle": "А123АА77",
                    "assigned_at": now - timedelta(hours=6),
                },
            },
            {
                "client": "ООО БетонСнаб",
                "cargo_type": concrete,
                "cargo_name": "Бетон М300 для фундамента",
                "cargo_weight": 14.0,
                "cargo_volume": None,
                "route_from": "Подольск, бетонный завод, 4",
                "route_to": "Москва, Кутузовский проспект, 55",
                "transportation_date": today,
                "cost": None,
                "comment": "Подача машины только после звонка прораба.",
                "status": "in_progress",
                "transportation": {
                    "driver": "Петров Петр Петрович",
                    "vehicle": "В456ВВ77",
                    "assigned_at": now - timedelta(hours=10),
                    "departure_at": now - timedelta(hours=2),
                },
            },
            {
                "client": "АО НерудПоставка",
                "cargo_type": crushed_stone,
                "cargo_name": "Щебень гранитный фракции 20-40",
                "cargo_weight": 19.2,
                "cargo_volume": None,
                "route_from": "Тула, карьер Южный, 9",
                "route_to": "Калуга, Заводской проезд, 7",
                "transportation_date": today - timedelta(days=2),
                "cost": None,
                "comment": "После разгрузки требуется фотоотчет.",
                "status": "completed",
                "transportation": {
                    "driver": "Сидоров Сергей Викторович",
                    "vehicle": "С789СС77",
                    "assigned_at": now - timedelta(days=3),
                    "departure_at": now - timedelta(days=2, hours=8),
                    "arrival_at": now - timedelta(days=2, hours=1),
                    "notes": "Доставлено без замечаний.",
                },
            },
            {
                "client": "ООО СкладЛогистик",
                "cargo_type": crushed_stone,
                "cargo_name": "Щебень известняковый фракции 5-20",
                "cargo_weight": 8.3,
                "cargo_volume": 24.5,
                "route_from": "Москва, Южный складской комплекс, 2",
                "route_to": "Тверь, ул. Коминтерна, 18",
                "transportation_date": today + timedelta(days=2),
                "cost": None,
                "comment": "Нужен чистый кузов, без остатков предыдущего груза.",
                "status": "processing",
            },
            {
                "client": "ООО МонолитСтрой",
                "cargo_type": concrete,
                "cargo_name": "Бетон М200 для стяжки",
                "cargo_weight": 9.4,
                "cargo_volume": 31.0,
                "route_from": "Домодедово, растворный узел, 6",
                "route_to": "Ярославль, Северная строительная база",
                "transportation_date": today + timedelta(days=3),
                "cost": None,
                "comment": "Поставка в первую половину дня.",
                "status": "new",
            },
            {
                "client": "ИП Петров",
                "cargo_type": sand,
                "cargo_name": "Песок карьерный мытый",
                "cargo_weight": 20.0,
                "cargo_volume": None,
                "route_from": "Московская область, карьер Березовый",
                "route_to": "Одинцово, строительная площадка Союзная",
                "transportation_date": today - timedelta(days=1),
                "cost": None,
                "comment": "Отменено заказчиком из-за переноса графика работ.",
                "status": "cancelled",
            },
            {
                "client": "ООО СеверСтрой",
                "cargo_type": sand,
                "cargo_name": "Песок речной для благоустройства",
                "cargo_weight": 4.8,
                "cargo_volume": 39.0,
                "route_from": "Клин, склад строительных материалов",
                "route_to": "Зеленоград, площадка бизнес-центра",
                "transportation_date": today + timedelta(days=4),
                "cost": None,
                "comment": "Разгрузка самосвалом на подготовленную площадку.",
                "status": "assigned",
                "transportation": {
                    "driver": "Кузнецов Алексей Игоревич",
                    "vehicle": "Е222КК77",
                    "assigned_at": now - timedelta(hours=3),
                },
            },
            {
                "client": "ООО СтройТранс",
                "cargo_type": crushed_stone,
                "cargo_name": "Щебень гравийный фракции 40-70",
                "cargo_weight": 12.7,
                "cargo_volume": None,
                "route_from": "Люберцы, база нерудных материалов, 11",
                "route_to": "Видное, коттеджный поселок Сосны",
                "transportation_date": today + timedelta(days=5),
                "cost": None,
                "comment": "Доставка одной партией, без разделения рейса.",
                "status": "processing",
            },
            {
                "client": "ООО ДорСнаб",
                "cargo_type": sand,
                "cargo_name": "Песок сеяный для дорожных работ",
                "cargo_weight": 13.5,
                "cargo_volume": None,
                "route_from": "Раменское, карьер Центральный, 3",
                "route_to": "Балашиха, дорожный участок Восточный",
                "transportation_date": today - timedelta(days=3),
                "cost": None,
                "comment": "Погрузка строго по пропуску подрядчика.",
                "status": "completed",
                "transportation": {
                    "driver": "Орлов Максим Андреевич",
                    "vehicle": "Н777НР77",
                    "assigned_at": now - timedelta(days=4),
                    "departure_at": now - timedelta(days=3, hours=7),
                    "arrival_at": now - timedelta(days=3, hours=1),
                    "notes": "Рейс закрыт, путевой лист подписан.",
                },
            },
            {
                "client": "ООО ГрадИнвест",
                "cargo_type": concrete,
                "cargo_name": "Бетон М400 для колонн",
                "cargo_weight": 15.8,
                "cargo_volume": None,
                "route_from": "Подольск, бетонный узел Северный, 2",
                "route_to": "Москва, ЖК Речной квартал, секция 4",
                "transportation_date": today + timedelta(days=1),
                "cost": None,
                "comment": "Подача к 08:30, сопровождение технадзора.",
                "status": "assigned",
                "transportation": {
                    "driver": "Смирнов Андрей Олегович",
                    "vehicle": "Р888РР77",
                    "assigned_at": now - timedelta(hours=5),
                },
            },
            {
                "client": "ООО РегионСтрой",
                "cargo_type": crushed_stone,
                "cargo_name": "Щебень гранитный для основания дороги",
                "cargo_weight": 16.4,
                "cargo_volume": None,
                "route_from": "Тверь, перевалочная база, 14",
                "route_to": "Клин, трасса М-11, участок 5",
                "transportation_date": today + timedelta(days=2),
                "cost": None,
                "comment": "Нужна разгрузка в две карты участка.",
                "status": "new",
            },
            {
                "client": "ООО ТехноБетон",
                "cargo_type": concrete,
                "cargo_name": "Бетон В25 с пластификатором",
                "cargo_weight": 11.2,
                "cargo_volume": None,
                "route_from": "Домодедово, РБУ Южный, 7",
                "route_to": "Подольск, производственный корпус 2",
                "transportation_date": today,
                "cost": None,
                "comment": "Не допускать простой машины более 30 минут.",
                "status": "in_progress",
                "transportation": {
                    "driver": "Орлов Максим Андреевич",
                    "vehicle": "Н777НР77",
                    "assigned_at": now - timedelta(hours=12),
                    "departure_at": now - timedelta(hours=1, minutes=40),
                },
            },
            {
                "client": "ООО МосИнерт",
                "cargo_type": sand,
                "cargo_name": "Песок для обратной засыпки",
                "cargo_weight": 9.7,
                "cargo_volume": 18.0,
                "route_from": "Люберцы, склад инертных материалов, 5",
                "route_to": "Мытищи, стройплощадка квартал Северный",
                "transportation_date": today + timedelta(days=3),
                "cost": None,
                "comment": "Заезд через КПП №2, водитель должен позвонить за 1 час.",
                "status": "processing",
            },
            {
                "client": "ООО ДорСнаб",
                "cargo_type": sand,
                "cargo_name": "Песок карьерный для зимнего хранения",
                "cargo_weight": 7.4,
                "cargo_volume": None,
                "route_from": "Ногинск, песчаная площадка 1",
                "route_to": "Электросталь, база хранения №3",
                "transportation_date": today + timedelta(days=4),
                "cost": None,
                "comment": "Доставка перенесена клиентом на следующую неделю.",
                "status": "cancelled",
            },
            {
                "client": "ООО БетонСнаб",
                "cargo_type": crushed_stone,
                "cargo_name": "Щебень для дренажного слоя",
                "cargo_weight": 9.5,
                "cargo_volume": None,
                "route_from": "Подольск, нерудный склад, 6",
                "route_to": "Чехов, коттеджный поселок Озерный",
                "transportation_date": today + timedelta(days=2),
                "cost": None,
                "comment": "Разгрузка только в присутствии мастера участка.",
                "status": "assigned",
                "transportation": {
                    "driver": "Васильев Дмитрий Сергеевич",
                    "vehicle": "Т909ТТ77",
                    "assigned_at": now - timedelta(hours=4),
                },
            },
            {
                "client": "ООО ГрадИнвест",
                "cargo_type": concrete,
                "cargo_name": "Бетон М250 для плиты перекрытия",
                "cargo_weight": 17.4,
                "cargo_volume": None,
                "route_from": "Химки, бетонный узел Западный, 1",
                "route_to": "Красногорск, бизнес-центр Skyline",
                "transportation_date": today - timedelta(days=4),
                "cost": None,
                "comment": "Доставка выполнена в ночную смену.",
                "status": "completed",
                "transportation": {
                    "driver": "Федоров Николай Павлович",
                    "vehicle": "О666ОО77",
                    "assigned_at": now - timedelta(days=5),
                    "departure_at": now - timedelta(days=4, hours=6),
                    "arrival_at": now - timedelta(days=4, hours=1),
                    "notes": "Заказчик принял без замечаний.",
                },
            },
            {
                "client": "ООО ТехноБетон",
                "cargo_type": crushed_stone,
                "cargo_name": "Щебень фракции 5-10 для бетонного производства",
                "cargo_weight": 14.3,
                "cargo_volume": None,
                "route_from": "Серпухов, база сырья, 12",
                "route_to": "Подольск, бетонный узел Южный, 9",
                "transportation_date": today + timedelta(days=5),
                "cost": None,
                "comment": "Поставка на утреннее окно до 09:00.",
                "status": "processing",
            },
            {
                "client": "ООО РегионСтрой",
                "cargo_type": sand,
                "cargo_name": "Песок мытый для благоустройства двора",
                "cargo_weight": 4.2,
                "cargo_volume": 11.0,
                "route_from": "Солнечногорск, песчаный склад, 8",
                "route_to": "Зеленоград, микрорайон 23, двор 2",
                "transportation_date": today + timedelta(days=1),
                "cost": None,
                "comment": "Нужен малотоннажный транспорт для въезда во двор.",
                "status": "assigned",
                "transportation": {
                    "driver": "Новиков Артем Евгеньевич",
                    "vehicle": "М555ММ77",
                    "assigned_at": now - timedelta(hours=2),
                },
            },
        ]

    def _ensure_admin(self):
        user, created = User.objects.get_or_create(
            username="admin",
            defaults={"email": "admin@example.com", "is_staff": True, "is_superuser": True},
        )
        if created:
            user.set_password("admin12345")
            user.save(update_fields=["password"])
        elif not user.is_superuser:
            user.is_staff = True
            user.is_superuser = True
            user.save(update_fields=["is_staff", "is_superuser"])

        user.profile.role = "admin"
        user.profile.save(update_fields=["role"])
        return user

    def _seed_clients(self):
        client_specs = [
            (
                "ООО СтройТранс",
                "+79000000001",
                "info@stroytrans.ru",
                "Москва, ул. Деловая, 10",
                "Ключевой заказчик по строительным материалам.",
            ),
            (
                "ООО БетонСнаб",
                "+79000000002",
                "dispatch@betonsnab.ru",
                "Подольск, ул. Заводская, 4",
                "Регулярные поставки бетонных смесей.",
            ),
            (
                "ИП Петров",
                "+79000000003",
                "petrov@example.com",
                "Одинцово, ул. Союзная, 18",
                "Частный заказчик строительных материалов.",
            ),
            (
                "АО НерудПоставка",
                "+79000000004",
                "office@nerudpost.ru",
                "Тула, ул. Карьерная, 21",
                "Поставки щебня и песка для объектов ЦФО.",
            ),
            (
                "ООО СкладЛогистик",
                "+79000000005",
                "ops@skladlog.ru",
                "Москва, Варшавское шоссе, 125",
                "Промежуточное хранение и отгрузка нерудных материалов.",
            ),
            (
                "ООО МонолитСтрой",
                "+79000000006",
                "zakaz@monolitstroy.ru",
                "Домодедово, промышленный парк, 8",
                "Заказчик бетонных смесей для монолитных работ.",
            ),
            (
                "ООО СеверСтрой",
                "+79000000007",
                "supply@severstroy.ru",
                "Клин, ул. Индустриальная, 3",
                "Строительные площадки северного направления.",
            ),
            (
                "ООО ДорСнаб",
                "+79000000008",
                "log@dorsnab.ru",
                "Балашиха, Западная промзона, 4",
                "Поставки материалов для дорожного строительства и ремонта.",
            ),
            (
                "ООО ГрадИнвест",
                "+79000000009",
                "supply@gradinvest.ru",
                "Москва, ул. Академика Королева, 17",
                "Девелопер жилых и коммерческих объектов в Московском регионе.",
            ),
            (
                "ООО РегионСтрой",
                "+79000000010",
                "office@regionstroy.ru",
                "Тверь, ул. Линейная, 12",
                "Генподрядчик по региональным строительным объектам.",
            ),
            (
                "ООО ТехноБетон",
                "+79000000011",
                "dispatch@technobeton.ru",
                "Подольск, ул. Бетонная, 5",
                "Производство и доставка товарного бетона.",
            ),
            (
                "ООО МосИнерт",
                "+79000000012",
                "info@mosinert.ru",
                "Люберцы, Проектируемый проезд, 9",
                "Поставщик песка и щебня для объектов Москвы и области.",
            ),
        ]
        clients = {}
        for name, phone, email, address, notes in client_specs:
            client, created = Client.objects.get_or_create(
                phone=phone,
                defaults={"name": name, "email": email, "address": address, "notes": notes},
            )
            if not created:
                client.name = name
                client.email = email
                client.address = address
                client.notes = notes
                client.save(update_fields=["name", "email", "address", "notes"])
            clients[name] = client
        return clients

    def _seed_drivers(self):
        driver_specs = [
            ("Иванов Иван Иванович", "+79000000101", "ВУ-101"),
            ("Петров Петр Петрович", "+79000000102", "ВУ-102"),
            ("Сидоров Сергей Викторович", "+79000000103", "ВУ-103"),
            ("Кузнецов Алексей Игоревич", "+79000000104", "ВУ-104"),
            ("Орлов Максим Андреевич", "+79000000105", "ВУ-105"),
            ("Смирнов Андрей Олегович", "+79000000106", "ВУ-106"),
            ("Федоров Николай Павлович", "+79000000107", "ВУ-107"),
            ("Васильев Дмитрий Сергеевич", "+79000000108", "ВУ-108"),
            ("Новиков Артем Евгеньевич", "+79000000109", "ВУ-109"),
        ]
        drivers = {}
        for full_name, phone, license_number in driver_specs:
            driver, created = Driver.objects.get_or_create(
                phone=phone,
                defaults={"full_name": full_name, "license_number": license_number},
            )
            if not created:
                driver.full_name = full_name
                driver.license_number = license_number
                driver.save(update_fields=["full_name", "license_number"])
            drivers[full_name] = driver
        return drivers

    def _seed_vehicles(self):
        vehicle_specs = [
            ("А123АА77", "A123AA77", "КамАЗ", "65115", 20),
            ("В456ВВ77", "B456BB77", "МАЗ", "6501", 18),
            ("С789СС77", "C789CC77", "КамАЗ", "6520", 20),
            ("Е222КК77", "E222KK77", "Урал", "Next", 12),
            ("М555ММ77", "M555MM77", "ГАЗ", "Садко Next", 5),
            ("Н777НР77", "Н777НР77", "МАЗ", "5516", 15),
            ("О666ОО77", "О666ОО77", "Shacman", "X3000", 25),
            ("Р888РР77", "Р888РР77", "КамАЗ", "6580", 20),
            ("Т909ТТ77", "Т909ТТ77", "Howo", "T5G", 16),
        ]
        vehicles = {}
        for registration_number, old_registration_number, brand, model, capacity_tons in vehicle_specs:
            vehicle = Vehicle.objects.filter(registration_number=registration_number).first()
            old_vehicle = Vehicle.objects.filter(registration_number=old_registration_number).first()

            if vehicle is not None and old_vehicle is not None and vehicle.pk != old_vehicle.pk:
                if not Transportation.objects.filter(vehicle=old_vehicle).exists():
                    old_vehicle.delete()
            elif vehicle is None:
                vehicle = old_vehicle

            if vehicle is None:
                vehicle = Vehicle.objects.create(
                    registration_number=registration_number,
                    brand=brand,
                    model=model,
                    capacity_tons=capacity_tons,
                )
            else:
                vehicle.registration_number = registration_number
                vehicle.brand = brand
                vehicle.model = model
                vehicle.capacity_tons = capacity_tons
                vehicle.save(update_fields=["registration_number", "brand", "model", "capacity_tons"])
            vehicles[registration_number] = vehicle
        return vehicles

    def _reset_demo_requests(self, clients):
        demo_client_ids = [client.pk for client in clients.values()]
        TransportationRequest.objects.filter(client_id__in=demo_client_ids).delete()

    def _upsert_request(self, spec, clients, statuses, admin_user):
        cargo_weight = Decimal(str(spec["cargo_weight"])) if spec["cargo_weight"] is not None else None
        cargo_volume = Decimal(str(spec["cargo_volume"])) if spec["cargo_volume"] is not None else None
        cost = Decimal(str(spec["cost"])) if spec.get("cost") is not None else None
        lookup = {
            "client": clients[spec["client"]],
            "cargo_type": spec["cargo_type"],
            "cargo_name": spec["cargo_name"],
            "route_from": spec["route_from"],
            "route_to": spec["route_to"],
        }

        request_obj = (
            TransportationRequest.objects.filter(**lookup)
            .order_by("created_at", "pk")
            .first()
        )

        if request_obj is None:
            return TransportationRequest.objects.create(
                **lookup,
                transportation_date=spec["transportation_date"],
                cargo_weight=cargo_weight,
                cargo_volume=cargo_volume,
                cost=cost,
                comment=spec["comment"],
                status=statuses["processing"] if spec.get("transportation") else statuses[spec["status"]],
                created_by=admin_user,
            )

        request_obj.transportation_date = spec["transportation_date"]
        request_obj.cargo_type = spec["cargo_type"]
        request_obj.cargo_weight = cargo_weight
        request_obj.cargo_volume = cargo_volume
        request_obj.cost = cost
        request_obj.comment = spec["comment"]
        request_obj.created_by = request_obj.created_by or admin_user
        request_obj.save(
            update_fields=[
                "transportation_date",
                "cargo_type",
                "cargo_weight",
                "cargo_volume",
                "cost",
                "comment",
                "created_by",
                "updated_at",
            ]
        )
        return request_obj

    def _upsert_transportation(self, spec, request_obj, drivers, vehicles, statuses, admin_user):
        transportation_spec = spec.get("transportation")
        if not transportation_spec:
            return

        transportation = Transportation.objects.filter(request=request_obj).first()
        if transportation is None and (request_obj.archived or request_obj.is_terminal):
            request_obj.status = statuses["processing"]
            request_obj.archived = False
            request_obj._status_changed_by = admin_user
            request_obj.save(update_fields=["status", "archived", "updated_at"])

        if transportation is None:
            transportation = Transportation(request=request_obj)

        if request_obj.archived or request_obj.is_terminal:
            return

        transportation.driver = drivers[transportation_spec["driver"]]
        transportation.vehicle = vehicles[transportation_spec["vehicle"]]
        transportation.assigned_at = transportation_spec.get("assigned_at", timezone.now())
        transportation.departure_at = transportation_spec.get("departure_at")
        transportation.arrival_at = transportation_spec.get("arrival_at")
        transportation.notes = transportation_spec.get("notes", "")
        transportation._acting_user = admin_user
        transportation.save()

    def _apply_final_status(self, spec, request_obj, statuses, admin_user):
        final_status = statuses[spec["status"]]
        if request_obj.status_id == final_status.id:
            return

        request_obj.status = final_status
        request_obj._status_changed_by = admin_user
        request_obj.save(update_fields=["status", "archived", "updated_at"])
