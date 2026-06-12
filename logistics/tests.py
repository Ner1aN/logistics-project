from datetime import date
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import Client, Driver, RequestStatus, Transportation, TransportationRequest, Vehicle, ensure_default_statuses


class LogisticsFlowTests(TestCase):
    def setUp(self):
        ensure_default_statuses()
        self.user = User.objects.create_user(username='manager', password='manager12345')
        self.client.force_login(self.user)
        self.customer = Client.objects.create(name='ООО Тест', phone='+79990000000')
        self.driver = Driver.objects.create(full_name='Иванов Иван Иванович', phone='+79990000001', license_number='ABC123')
        self.vehicle = Vehicle.objects.create(registration_number='А123АА77', brand='КамАЗ', model='65115', capacity_tons=10)
        self.status_new = RequestStatus.objects.get(code='new')
        self.status_processing = RequestStatus.objects.get(code='processing')
        self.status_completed = RequestStatus.objects.get(code='completed')

    def _create_request(self, status=None, **kwargs):
        payload = {
            'client': self.customer,
            'cargo_type': TransportationRequest.CargoType.CRUSHED_STONE,
            'cargo_name': 'Щебень',
            'cargo_weight': '8.50',
            'route_from': 'Склад',
            'route_to': 'Объект',
            'transportation_date': '2026-04-15',
            'cost': '12000.00',
            'status': status or self.status_new,
            'created_by': self.user,
        }
        payload.update(kwargs)
        request_obj = TransportationRequest.objects.create(**payload)
        return request_obj

    def test_create_request_creates_status_history(self):
        response = self.client.post(
            reverse('request-create'),
            {
                'client': self.customer.pk,
                'cargo_type': TransportationRequest.CargoType.CRUSHED_STONE,
                'cargo_name': 'Щебень',
                'cargo_weight': '8.50',
                'cargo_volume': '',
                'route_from': 'Склад',
                'route_to': 'Объект',
                'transportation_date': '2026-04-15',
                'cost': '12000.00',
                'status': self.status_new.pk,
                'comment': 'Тестовая перевозка',
            },
        )
        self.assertEqual(response.status_code, 302)
        request_obj = TransportationRequest.objects.get()
        self.assertEqual(request_obj.status_history.count(), 1)
        self.assertEqual(request_obj.status_history.first().status, self.status_new)

    def test_request_detail_page_available(self):
        request_obj = self._create_request()
        response = self.client.get(reverse('request-detail', args=[request_obj.pk]))
        self.assertContains(response, 'Заявка')
        self.assertContains(response, 'Щебень')

    def test_request_transportation_date_is_saved_on_edit(self):
        request_obj = self._create_request()
        response = self.client.post(
            reverse('request-edit', args=[request_obj.pk]),
            {
                'client': self.customer.pk,
                'cargo_type': TransportationRequest.CargoType.CRUSHED_STONE,
                'cargo_name': 'Щебень',
                'cargo_weight': '8.50',
                'cargo_volume': '',
                'route_from': 'Склад',
                'route_to': 'Объект',
                'transportation_date': '2026-06-11',
                'cost': '12000.00',
                'status': self.status_new.pk,
                'comment': 'Изменение даты',
            },
        )

        self.assertEqual(response.status_code, 302)
        request_obj.refresh_from_db()
        self.assertEqual(str(request_obj.transportation_date), '2026-06-11')

    def test_request_cost_is_calculated_when_blank(self):
        request_obj = TransportationRequest.objects.create(
            client=self.customer,
            cargo_type=TransportationRequest.CargoType.CONCRETE,
            cargo_name='Автоматический расчет',
            cargo_weight=Decimal('8.50'),
            route_from='Склад',
            route_to='Объект',
            transportation_date='2026-04-15',
            status=self.status_new,
            created_by=self.user,
        )

        self.assertEqual(request_obj.cost, Decimal('12200.00'))

    def test_request_cost_is_calculated_by_volume_when_weight_blank(self):
        request_obj = TransportationRequest.objects.create(
            client=self.customer,
            cargo_type=TransportationRequest.CargoType.SAND,
            cargo_name='Песок по объему',
            cargo_volume=Decimal('10.00'),
            route_from='Склад',
            route_to='Объект',
            transportation_date='2026-04-15',
            status=self.status_new,
            created_by=self.user,
        )

        self.assertEqual(request_obj.cost, Decimal('5500.00'))

    def test_manual_request_cost_is_not_overwritten(self):
        request_obj = TransportationRequest.objects.create(
            client=self.customer,
            cargo_type=TransportationRequest.CargoType.SAND,
            cargo_name='Ручная стоимость',
            cargo_weight=Decimal('8.50'),
            route_from='Склад',
            route_to='Объект',
            transportation_date='2026-04-15',
            cost=Decimal('12345.00'),
            status=self.status_new,
            created_by=self.user,
        )

        self.assertEqual(request_obj.cost, Decimal('12345.00'))

    def test_auto_request_cost_is_recalculated_when_weight_changes_on_edit(self):
        request_obj = TransportationRequest.objects.create(
            client=self.customer,
            cargo_type=TransportationRequest.CargoType.CONCRETE,
            cargo_name='Concrete',
            cargo_weight=Decimal('8.50'),
            route_from='Warehouse',
            route_to='Site',
            transportation_date='2026-04-15',
            status=self.status_new,
            created_by=self.user,
        )

        response = self.client.post(
            reverse('request-edit', args=[request_obj.pk]),
            {
                'client': self.customer.pk,
                'cargo_type': TransportationRequest.CargoType.CONCRETE,
                'cargo_name': 'Concrete',
                'cargo_weight': '10.00',
                'cargo_volume': '',
                'route_from': 'Warehouse',
                'route_to': 'Site',
                'transportation_date': '2026-04-15',
                'cost': '12200.00',
                'status': self.status_new.pk,
                'comment': '',
            },
        )

        self.assertEqual(response.status_code, 302)
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.cost, Decimal('14000.00'))

    def test_cannot_assign_busy_driver_and_vehicle_to_active_request(self):
        first_request = self._create_request(status=self.status_processing)
        first_transportation = Transportation(
            request=first_request,
            driver=self.driver,
            vehicle=self.vehicle,
        )
        first_transportation._acting_user = self.user
        first_transportation.save()

        second_request = self._create_request(status=self.status_processing, route_to='Второй объект')
        response = self.client.post(
            reverse('request-assign', args=[second_request.pk]),
            {
                'driver': self.driver.pk,
                'vehicle': self.vehicle.pk,
                'trip_count': '1',
                'distance_parking_to_loading_km': '0',
                'distance_loading_to_customer_km': '0',
                'distance_customer_to_loading_km': '0',
                'assigned_at': '2026-04-15T10:00',
                'departure_at': '',
                'arrival_at': '',
                'notes': 'Повторное назначение',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Водитель уже назначен')
        self.assertContains(response, 'Транспорт уже назначен')
        self.assertFalse(second_request.transportations.exists())

    def test_can_assign_vehicle_when_single_vehicle_capacity_is_partial(self):
        request_obj = self._create_request(
            status=self.status_processing,
            cargo_weight=Decimal('12.00'),
            cost=Decimal('15000.00'),
        )
        response = self.client.post(
            reverse('request-assign', args=[request_obj.pk]),
            {
                'driver': self.driver.pk,
                'vehicle': self.vehicle.pk,
                'trip_count': '1',
                'distance_parking_to_loading_km': '0',
                'distance_loading_to_customer_km': '0',
                'distance_customer_to_loading_km': '0',
                'assigned_at': '2026-04-15T10:00',
                'departure_at': '',
                'arrival_at': '',
                'notes': 'Проверка грузоподъемности',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(request_obj.transportations.count(), 1)

    def test_can_assign_multiple_trips_and_recalculate_cost_by_distance(self):
        request_obj = TransportationRequest.objects.create(
            client=self.customer,
            cargo_type=TransportationRequest.CargoType.SAND,
            cargo_name='Sand',
            cargo_weight=Decimal('12.00'),
            route_from='Warehouse',
            route_to='Site',
            transportation_date='2026-04-15',
            status=self.status_processing,
            created_by=self.user,
        )

        response = self.client.post(
            reverse('request-assign', args=[request_obj.pk]),
            {
                'driver': self.driver.pk,
                'vehicle': self.vehicle.pk,
                'trip_count': '2',
                'distance_parking_to_loading_km': '5',
                'distance_loading_to_customer_km': '20',
                'distance_customer_to_loading_km': '18',
                'assigned_at': '2026-04-15T10:00',
                'departure_at': '',
                'arrival_at': '',
                'notes': 'Two trips',
            },
        )

        self.assertEqual(response.status_code, 302)
        request_obj.refresh_from_db()
        transportation = request_obj.transportations.get()
        self.assertEqual(transportation.trip_count, 2)
        self.assertEqual(transportation.total_distance_km, Decimal('63.00'))
        self.assertEqual(transportation.load_percent, Decimal('60.0'))
        self.assertEqual(request_obj.cost, Decimal('14900.00'))

    def test_can_assign_multiple_vehicles_to_one_request(self):
        second_driver = Driver.objects.create(full_name='Second Driver', phone='+79990000002', license_number='XYZ456')
        second_vehicle = Vehicle.objects.create(registration_number='B456BB77', brand='MAZ', model='6501', capacity_tons=8)
        request_obj = TransportationRequest.objects.create(
            client=self.customer,
            cargo_type=TransportationRequest.CargoType.CRUSHED_STONE,
            cargo_name='Crushed stone',
            cargo_weight=Decimal('18.00'),
            route_from='Warehouse',
            route_to='Site',
            transportation_date='2026-04-15',
            status=self.status_processing,
            created_by=self.user,
        )

        first = Transportation.objects.create(
            request=request_obj,
            driver=self.driver,
            vehicle=self.vehicle,
            trip_count=1,
            distance_parking_to_loading_km=Decimal('5.00'),
            distance_loading_to_customer_km=Decimal('20.00'),
            distance_customer_to_loading_km=Decimal('0.00'),
        )
        second = Transportation.objects.create(
            request=request_obj,
            driver=second_driver,
            vehicle=second_vehicle,
            trip_count=1,
            distance_parking_to_loading_km=Decimal('6.00'),
            distance_loading_to_customer_km=Decimal('18.00'),
            distance_customer_to_loading_km=Decimal('0.00'),
        )

        request_obj.refresh_from_db()
        self.assertEqual(request_obj.transportations.count(), 2)
        self.assertEqual(request_obj.assigned_capacity_tons(), Decimal('18.00'))
        self.assertEqual(request_obj.total_distance_km(), Decimal('49.00'))
        self.assertEqual(request_obj.cost, Decimal('18600.00'))
        self.assertEqual({first.vehicle_id, second.vehicle_id}, set(request_obj.transportations.values_list('vehicle_id', flat=True)))

    def test_can_increase_request_weight_after_assignment(self):
        request_obj = self._create_request(status=self.status_processing, cargo_weight=Decimal('8.00'))
        transportation = Transportation(
            request=request_obj,
            driver=self.driver,
            vehicle=self.vehicle,
        )
        transportation._acting_user = self.user
        transportation.save()

        response = self.client.post(
            reverse('request-edit', args=[request_obj.pk]),
            {
                'client': self.customer.pk,
                'cargo_type': TransportationRequest.CargoType.CRUSHED_STONE,
                'cargo_name': 'Щебень',
                'cargo_weight': '12.00',
                'cargo_volume': '',
                'route_from': 'Склад',
                'route_to': 'Объект',
                'transportation_date': '2026-04-15',
                'cost': '12000.00',
                'status': self.status_processing.pk,
                'comment': 'Проверка превышения после назначения',
            },
        )

        self.assertEqual(response.status_code, 302)
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.cargo_weight, Decimal('12.00'))

    def test_completed_request_moves_to_archive_and_releases_resources(self):
        request_obj = self._create_request(status=self.status_processing)
        transportation = Transportation(
            request=request_obj,
            driver=self.driver,
            vehicle=self.vehicle,
        )
        transportation._acting_user = self.user
        transportation.save()

        request_obj.status = self.status_completed
        request_obj._status_changed_by = self.user
        request_obj.save(update_fields=['status', 'updated_at'])

        request_obj.refresh_from_db()
        self.driver.refresh_from_db()
        self.vehicle.refresh_from_db()

        self.assertTrue(request_obj.archived)
        self.assertTrue(self.driver.is_available)
        self.assertTrue(self.vehicle.is_available)
        self.assertEqual(request_obj.status_history.count(), 3)

    def test_reports_include_calculated_metrics(self):
        completed_request = self._create_request(
            status=self.status_processing,
            cargo_weight=Decimal('5.00'),
            cost=Decimal('10000.00'),
        )
        transportation = Transportation(
            request=completed_request,
            driver=self.driver,
            vehicle=self.vehicle,
        )
        transportation._acting_user = self.user
        transportation.save()
        completed_request.status = self.status_completed
        completed_request._status_changed_by = self.user
        completed_request.save(update_fields=['status', 'updated_at'])

        self._create_request(
            status=self.status_processing,
            route_to='Просроченный объект',
            cargo_weight=Decimal('4.00'),
            cost=Decimal('20000.00'),
        )

        response = self.client.get(reverse('reports'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['request_total_count'], 2)
        self.assertEqual(response.context['completed_request_count'], 1)
        self.assertEqual(response.context['completed_request_percent'], 50.0)
        self.assertEqual(response.context['overdue_request_count'], 1)
        self.assertEqual(response.context['average_request_cost'], Decimal('15000'))
        self.assertEqual(list(response.context['driver_load_chart']), [{'label': self.driver.full_name, 'count': 1}])

    def test_reports_pdf_export_available(self):
        self._create_request(status=self.status_completed, cargo_weight=Decimal('5.00'), cost=Decimal('10000.00'))

        response = self.client.get(reverse('reports-pdf'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_reports_excel_export_available(self):
        self._create_request(status=self.status_completed, cargo_weight=Decimal('5.00'), cost=Decimal('10000.00'))

        response = self.client.get(reverse('reports-excel'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertTrue(response.content.startswith(b'PK'))

    def test_seed_demo_can_be_repeated_on_another_day(self):
        with patch("logistics.management.commands.seed_demo.timezone.localdate", return_value=date(2026, 4, 16)):
            call_command("seed_demo", stdout=StringIO())

        first_request_count = TransportationRequest.objects.count()
        first_transportation_count = Transportation.objects.count()

        with patch("logistics.management.commands.seed_demo.timezone.localdate", return_value=date(2026, 4, 17)):
            call_command("seed_demo", stdout=StringIO())

        self.assertEqual(TransportationRequest.objects.count(), first_request_count)
        self.assertEqual(Transportation.objects.count(), first_transportation_count)

