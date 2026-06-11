from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Profile(models.Model):
    class Role(models.TextChoices):
        MANAGER = 'manager', 'Менеджер по логистике'
        LEADER = 'leader', 'Руководитель'
        ADMIN = 'admin', 'Администратор'

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MANAGER)

    def __str__(self):
        return f'{self.user.username} ({self.get_role_display()})'


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)


class Client(TimeStampedModel):
    name = models.CharField('Наименование клиента', max_length=255)
    phone = models.CharField('Телефон', max_length=30, unique=True)
    email = models.EmailField('Email', blank=True)
    address = models.CharField('Адрес', max_length=255, blank=True)
    notes = models.TextField('Комментарий', blank=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Клиент'
        verbose_name_plural = 'Клиенты'

    def __str__(self):
        return self.name


class Driver(TimeStampedModel):
    full_name = models.CharField('ФИО водителя', max_length=255)
    phone = models.CharField('Телефон', max_length=30, unique=True)
    license_number = models.CharField('Номер удостоверения', max_length=50, unique=True)
    is_available = models.BooleanField('Доступен', default=True)
    notes = models.TextField('Комментарий', blank=True)

    class Meta:
        ordering = ['full_name']
        verbose_name = 'Водитель'
        verbose_name_plural = 'Водители'

    def __str__(self):
        return self.full_name

    @property
    def active_transportation(self):
        return (
            active_transportations()
            .filter(driver_id=self.pk)
            .select_related('request', 'vehicle')
            .first()
        )


class Vehicle(TimeStampedModel):
    registration_number = models.CharField('Гос. номер', max_length=20, unique=True)
    brand = models.CharField('Марка', max_length=100)
    model = models.CharField('Модель', max_length=100, blank=True)
    capacity_tons = models.DecimalField('Грузоподъемность, т', max_digits=6, decimal_places=2)
    is_available = models.BooleanField('Доступно', default=True)
    notes = models.TextField('Комментарий', blank=True)

    class Meta:
        ordering = ['registration_number']
        verbose_name = 'Транспортное средство'
        verbose_name_plural = 'Транспортные средства'

    def __str__(self):
        return f'{self.registration_number} - {self.brand} {self.model}'.strip()

    @property
    def active_transportation(self):
        return (
            active_transportations()
            .filter(vehicle_id=self.pk)
            .select_related('request', 'driver')
            .first()
        )


class RequestStatus(models.Model):
    name = models.CharField('Название', max_length=100, unique=True)
    code = models.SlugField('Код', max_length=50, unique=True)
    order = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'Статус заявки'
        verbose_name_plural = 'Статусы заявок'

    def __str__(self):
        return self.name


class TransportationRequest(TimeStampedModel):
    class CargoType(models.TextChoices):
        SAND = 'sand', 'Песок'
        CRUSHED_STONE = 'crushed_stone', 'Щебень'
        CONCRETE = 'concrete', 'Бетон'

    TERMINAL_STATUS_CODES = {'completed', 'cancelled'}
    BASE_RATE = Decimal('2000')
    DISTANCE_RATE_PER_KM = Decimal('100')
    CARGO_TYPE_RATES = {
        CargoType.SAND: {
            'ton': Decimal('550'),
            'm3': Decimal('350'),
        },
        CargoType.CRUSHED_STONE: {
            'ton': Decimal('650'),
            'm3': Decimal('420'),
        },
        CargoType.CONCRETE: {
            'ton': Decimal('1200'),
            'm3': Decimal('900'),
        },
    }

    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='requests', verbose_name='Клиент')
    cargo_type = models.CharField('Тип груза', max_length=20, choices=CargoType.choices, default=CargoType.SAND)
    cargo_name = models.CharField('Описание груза', max_length=255)
    cargo_weight = models.DecimalField('Масса груза, т', max_digits=8, decimal_places=2, null=True, blank=True)
    cargo_volume = models.DecimalField('Объем груза, м3', max_digits=8, decimal_places=2, null=True, blank=True)
    route_from = models.CharField('Адрес загрузки', max_length=255)
    route_to = models.CharField('Адрес выгрузки', max_length=255)
    transportation_date = models.DateField('Дата перевозки')
    cost = models.DecimalField('Стоимость, ₽', max_digits=12, decimal_places=2)
    status = models.ForeignKey(RequestStatus, on_delete=models.PROTECT, related_name='requests', verbose_name='Статус')
    comment = models.TextField('Комментарий', blank=True)
    archived = models.BooleanField('В архиве', default=False)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_requests',
        verbose_name='Создал',
    )

    class Meta:
        ordering = ['-transportation_date', '-created_at']
        verbose_name = 'Заявка на перевозку'
        verbose_name_plural = 'Заявки на перевозку'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._loaded_status_id = self.status_id
        self._loaded_archived = self.archived

    def __str__(self):
        return f'Заявка #{self.pk} - {self.client.name}'

    @property
    def is_terminal(self):
        return self.status.code in self.TERMINAL_STATUS_CODES

    @property
    def is_active(self):
        return not self.archived and not self.is_terminal

    @property
    def cargo_summary(self):
        parts = []
        if self.cargo_weight is not None:
            parts.append(f'{self.cargo_weight} т')
        if self.cargo_volume is not None:
            parts.append(f'{self.cargo_volume} м3')
        return ' / '.join(parts) or 'Не указано'

    @property
    def cargo_tariff_summary(self):
        rates = self.get_cargo_rates()
        return f"{rates['ton']} ₽/т, {rates['m3']} ₽/м3, {self.DISTANCE_RATE_PER_KM} ₽/км"

    @property
    def status_badge_class(self):
        return {
            'new': 'primary',
            'processing': 'warning',
            'assigned': 'info',
            'in_progress': 'secondary',
            'completed': 'success',
            'cancelled': 'danger',
        }.get(self.status.code, 'secondary')

    def calculate_cargo_cost(self):
        rates = self.get_cargo_rates()
        if self.cargo_weight is not None:
            return (self.BASE_RATE + self.cargo_weight * rates['ton']).quantize(Decimal('0.01'))
        if self.cargo_volume is not None:
            return (self.BASE_RATE + self.cargo_volume * rates['m3']).quantize(Decimal('0.01'))
        return None

    def get_transportation_for_cost(self):
        if hasattr(self, 'transportation'):
            return self.transportation
        if self.pk:
            return Transportation.objects.filter(request=self).first()
        return None

    def calculate_distance_cost(self, transportation=None):
        transportation = transportation if transportation is not None else self.get_transportation_for_cost()
        if not transportation:
            return Decimal('0.00')
        return (transportation.total_distance_km * self.DISTANCE_RATE_PER_KM).quantize(Decimal('0.01'))

    def calculate_cost(self, transportation=None):
        cargo_cost = self.calculate_cargo_cost()
        if cargo_cost is None:
            return None
        return (cargo_cost + self.calculate_distance_cost(transportation)).quantize(Decimal('0.01'))

    def get_cargo_rates(self):
        return self.CARGO_TYPE_RATES.get(self.cargo_type, self.CARGO_TYPE_RATES[self.CargoType.SAND])

    def clean(self):
        super().clean()
        if self.cargo_weight is None and self.cargo_volume is None:
            message = 'Укажите массу или объем груза.'
            raise ValidationError({'cargo_weight': message, 'cargo_volume': message})

        transportation = None
        if self.pk:
            transportation = self.transportation if hasattr(self, 'transportation') else Transportation.objects.select_related('vehicle').filter(request=self).first()

        if transportation and self.cargo_weight is not None:
            vehicle_capacity = transportation.vehicle.capacity_tons
            trip_count = transportation.trip_count or 1
            total_capacity = vehicle_capacity * trip_count if vehicle_capacity else None
            if total_capacity and self.cargo_weight > total_capacity:
                raise ValidationError({
                    'cargo_weight': f'Масса груза превышает суммарную грузоподъемность назначенного транспорта за {trip_count} рейс(ов) ({total_capacity} т).'
                })

    def save(self, *args, **kwargs):
        cost_was_auto_calculated = getattr(self, '_cost_was_auto_calculated', False)
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            update_fields = set(update_fields)

        if self.cost in (None, ''):
            calculated_cost = self.calculate_cost()
            if calculated_cost is not None:
                self.cost = calculated_cost
                cost_was_auto_calculated = True
                if update_fields is not None:
                    update_fields.add('cost')

        status_code = None
        if self.status_id:
            status_code = self.status.code if hasattr(self, 'status') else RequestStatus.objects.filter(pk=self.status_id).values_list('code', flat=True).first()
        if status_code in self.TERMINAL_STATUS_CODES:
            self.archived = True
            if update_fields is not None:
                update_fields.add('archived')

        if update_fields is not None:
            kwargs['update_fields'] = update_fields

        self._cost_was_auto_calculated = cost_was_auto_calculated
        self.full_clean()

        is_create = self._state.adding
        previous_status_id = None if is_create else self._loaded_status_id
        previous_archived = None if is_create else self._loaded_archived

        super().save(*args, **kwargs)

        if is_create or previous_status_id != self.status_id:
            RequestStatusHistory.objects.create(
                request=self,
                status=self.status,
                changed_by=getattr(self, '_status_changed_by', None) or (self.created_by if is_create else None),
            )

        if is_create or previous_status_id != self.status_id or previous_archived != self.archived:
            sync_request_resource_availability(self)

        self._loaded_status_id = self.status_id
        self._loaded_archived = self.archived
        if hasattr(self, '_status_changed_by'):
            delattr(self, '_status_changed_by')


class RequestStatusHistory(models.Model):
    request = models.ForeignKey(
        TransportationRequest,
        on_delete=models.CASCADE,
        related_name='status_history',
        verbose_name='Заявка',
    )
    status = models.ForeignKey(RequestStatus, on_delete=models.PROTECT, related_name='history_entries', verbose_name='Статус')
    changed_at = models.DateTimeField('Дата изменения', auto_now_add=True)
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='request_status_changes',
        verbose_name='Пользователь',
    )

    class Meta:
        ordering = ['-changed_at', '-id']
        verbose_name = 'История статуса заявки'
        verbose_name_plural = 'История статусов заявок'

    def __str__(self):
        return f'#{self.request_id} - {self.status.name}'


class Transportation(TimeStampedModel):
    request = models.OneToOneField(
        TransportationRequest,
        on_delete=models.CASCADE,
        related_name='transportation',
        verbose_name='Заявка',
    )
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name='transportations', verbose_name='Транспорт')
    driver = models.ForeignKey(Driver, on_delete=models.PROTECT, related_name='transportations', verbose_name='Водитель')
    assigned_at = models.DateTimeField('Дата назначения', default=timezone.now)
    departure_at = models.DateTimeField('Дата начала', null=True, blank=True)
    arrival_at = models.DateTimeField('Дата завершения', null=True, blank=True)
    trip_count = models.PositiveIntegerField('Количество рейсов ТС', default=1)
    distance_parking_to_loading_km = models.DecimalField('Стоянка - место погрузки, км', max_digits=8, decimal_places=2, default=0)
    distance_loading_to_customer_km = models.DecimalField('Погрузка - заказчик, км', max_digits=8, decimal_places=2, default=0)
    distance_customer_to_loading_km = models.DecimalField('Заказчик - место погрузки, км', max_digits=8, decimal_places=2, default=0)
    notes = models.TextField('Примечание', blank=True)

    class Meta:
        ordering = ['-assigned_at', '-created_at']
        verbose_name = 'Перевозка'
        verbose_name_plural = 'Перевозки'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._loaded_driver_id = self.driver_id
        self._loaded_vehicle_id = self.vehicle_id

    @property
    def return_trip_count(self):
        return max((self.trip_count or 1) - 1, 0)

    @property
    def total_distance_km(self):
        return (
            (self.distance_parking_to_loading_km or Decimal('0'))
            + (self.distance_loading_to_customer_km or Decimal('0')) * (self.trip_count or 1)
            + (self.distance_customer_to_loading_km or Decimal('0')) * self.return_trip_count
        ).quantize(Decimal('0.01'))

    @property
    def distance_cost(self):
        return (self.total_distance_km * TransportationRequest.DISTANCE_RATE_PER_KM).quantize(Decimal('0.01'))

    @property
    def required_trip_count(self):
        if not self.request_id or not self.vehicle_id:
            return None
        if not hasattr(self, 'request') or not hasattr(self, 'vehicle'):
            return None
        if self.request.cargo_weight is None or not self.vehicle.capacity_tons:
            return None
        return int((self.request.cargo_weight / self.vehicle.capacity_tons).to_integral_value(rounding=ROUND_CEILING))

    @property
    def total_capacity_tons(self):
        if not self.vehicle_id or not hasattr(self, 'vehicle') or not self.vehicle.capacity_tons:
            return None
        return (self.vehicle.capacity_tons * (self.trip_count or 1)).quantize(Decimal('0.01'))

    @property
    def load_percent(self):
        if not self.request_id or not self.vehicle_id:
            return None

        if not hasattr(self, 'request') or not hasattr(self, 'vehicle'):
            return None

        if self.request.cargo_weight is None or not self.vehicle.capacity_tons:
            return None

        total_capacity = self.vehicle.capacity_tons * (self.trip_count or 1)
        if not total_capacity:
            return None

        return (
            self.request.cargo_weight / total_capacity * Decimal('100')
        ).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)

    def clean(self):
        super().clean()
        errors = {}
        if self.departure_at and self.arrival_at and self.arrival_at < self.departure_at:
            errors['arrival_at'] = 'Дата завершения не может быть раньше даты начала.'
        if not self.trip_count or self.trip_count < 1:
            errors['trip_count'] = 'Количество рейсов должно быть не меньше 1.'
        for field_name in [
            'distance_parking_to_loading_km',
            'distance_loading_to_customer_km',
            'distance_customer_to_loading_km',
        ]:
            if getattr(self, field_name) is not None and getattr(self, field_name) < 0:
                errors[field_name] = 'Километраж не может быть отрицательным.'

        request_obj = None
        if self.request_id:
            request_obj = self.request if hasattr(self, 'request') else TransportationRequest.objects.select_related('status').get(pk=self.request_id)
            if request_obj.archived or request_obj.is_terminal:
                errors['request'] = 'Нельзя назначить перевозку архивной или завершенной заявке.'

        if request_obj is not None and self.vehicle_id and request_obj.cargo_weight is not None:
            vehicle = self.vehicle if hasattr(self, 'vehicle') else Vehicle.objects.get(pk=self.vehicle_id)
            trip_count = self.trip_count or 1
            total_capacity = vehicle.capacity_tons * trip_count if vehicle.capacity_tons else None
            if total_capacity and request_obj.cargo_weight > total_capacity:
                required_trips = int((request_obj.cargo_weight / vehicle.capacity_tons).to_integral_value(rounding=ROUND_CEILING))
                errors['trip_count'] = f'Для этой массы груза нужно минимум {required_trips} рейс(ов) выбранного транспорта.'

        conflicts = active_transportations(exclude_transportation_id=self.pk)
        if self.driver_id:
            busy_transportation = conflicts.filter(driver_id=self.driver_id).select_related('request').first()
            if busy_transportation:
                errors['driver'] = f'Водитель уже назначен на активную заявку #{busy_transportation.request_id}.'
        if self.vehicle_id:
            busy_transportation = conflicts.filter(vehicle_id=self.vehicle_id).select_related('request').first()
            if busy_transportation:
                errors['vehicle'] = f'Транспорт уже назначен на активную заявку #{busy_transportation.request_id}.'

        if errors:
            raise ValidationError(errors)

    def _get_request_auto_cost_state(self):
        if not self.request_id:
            return None, set()

        request_obj = TransportationRequest.objects.filter(pk=self.request_id).first()
        if request_obj is None:
            return None, set()

        candidates = {
            request_obj.calculate_cargo_cost(),
            request_obj.calculate_cost(),
        }
        return request_obj, {value for value in candidates if value is not None}

    def save(self, *args, **kwargs):
        self.full_clean()
        request_obj, previous_auto_costs = self._get_request_auto_cost_state()

        previous_driver_id = None if self._state.adding else self._loaded_driver_id
        previous_vehicle_id = None if self._state.adding else self._loaded_vehicle_id

        super().save(*args, **kwargs)

        if request_obj is not None and request_obj.cost in previous_auto_costs:
            new_cost = request_obj.calculate_cost(transportation=self)
            if new_cost is not None and request_obj.cost != new_cost:
                request_obj.cost = new_cost
                request_obj._cost_was_auto_calculated = True
                request_obj.save(update_fields=['cost', 'updated_at'])

        if self.request.status.code in {'new', 'processing'}:
            assigned_status = get_status('assigned')
            if assigned_status and self.request.status_id != assigned_status.id:
                self.request.status = assigned_status
                self.request._status_changed_by = getattr(self, '_acting_user', None)
                self.request.save(update_fields=['status', 'archived', 'updated_at'])

        refresh_resource_availability(
            driver_ids={driver_id for driver_id in {previous_driver_id, self.driver_id} if driver_id},
            vehicle_ids={vehicle_id for vehicle_id in {previous_vehicle_id, self.vehicle_id} if vehicle_id},
        )

        self._loaded_driver_id = self.driver_id
        self._loaded_vehicle_id = self.vehicle_id
        if hasattr(self, '_acting_user'):
            delattr(self, '_acting_user')

    def delete(self, *args, **kwargs):
        driver_id = self.driver_id
        vehicle_id = self.vehicle_id
        request_obj = self.request
        super().delete(*args, **kwargs)
        refresh_resource_availability(driver_ids={driver_id}, vehicle_ids={vehicle_id})
        if request_obj.status.code == 'assigned':
            processing_status = get_status('processing')
            if processing_status:
                request_obj.status = processing_status
                request_obj.save(update_fields=['status', 'updated_at'])

    def __str__(self):
        return f'Перевозка по заявке #{self.request_id}'


def get_status(code: str):
    return RequestStatus.objects.filter(code=code).first()


def active_transportations(exclude_transportation_id=None):
    queryset = Transportation.objects.filter(request__archived=False).exclude(request__status__code__in=TransportationRequest.TERMINAL_STATUS_CODES)
    if exclude_transportation_id:
        queryset = queryset.exclude(pk=exclude_transportation_id)
    return queryset


def refresh_resource_availability(driver_ids=None, vehicle_ids=None):
    driver_ids = {driver_id for driver_id in (driver_ids or set()) if driver_id}
    vehicle_ids = {vehicle_id for vehicle_id in (vehicle_ids or set()) if vehicle_id}

    if driver_ids:
        busy_driver_ids = set(active_transportations().filter(driver_id__in=driver_ids).values_list('driver_id', flat=True))
        for driver in Driver.objects.filter(pk__in=driver_ids):
            should_be_available = driver.pk not in busy_driver_ids
            if driver.is_available != should_be_available:
                driver.is_available = should_be_available
                driver.save(update_fields=['is_available'])

    if vehicle_ids:
        busy_vehicle_ids = set(active_transportations().filter(vehicle_id__in=vehicle_ids).values_list('vehicle_id', flat=True))
        for vehicle in Vehicle.objects.filter(pk__in=vehicle_ids):
            should_be_available = vehicle.pk not in busy_vehicle_ids
            if vehicle.is_available != should_be_available:
                vehicle.is_available = should_be_available
                vehicle.save(update_fields=['is_available'])


def sync_request_resource_availability(request_obj: TransportationRequest):
    transportation = getattr(request_obj, 'transportation', None)
    if transportation is None:
        return

    refresh_resource_availability(
        driver_ids={transportation.driver_id},
        vehicle_ids={transportation.vehicle_id},
    )


def refresh_all_resource_availability():
    refresh_resource_availability(
        driver_ids=set(Driver.objects.values_list('id', flat=True)),
        vehicle_ids=set(Vehicle.objects.values_list('id', flat=True)),
    )


def ensure_default_statuses():
    defaults = [
        ('new', 'Новая', 1),
        ('processing', 'В обработке', 2),
        ('assigned', 'Назначена', 3),
        ('in_progress', 'Выполняется', 4),
        ('completed', 'Выполнена', 5),
        ('cancelled', 'Отменена', 6),
    ]
    for code, name, order in defaults:
        RequestStatus.objects.get_or_create(code=code, defaults={'name': name, 'order': order})
