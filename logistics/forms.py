from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Q

from .models import Client, Driver, RequestStatus, Transportation, TransportationRequest, Vehicle


class StyledFormMixin:
    def _apply_bootstrap(self):
        for field in self.fields.values():
            widget = field.widget
            base_class = 'form-check-input' if isinstance(widget, forms.CheckboxInput) else 'form-control'
            if isinstance(widget, forms.Select):
                base_class = 'form-select'
            existing = widget.attrs.get('class', '')
            widget.attrs['class'] = f'{existing} {base_class}'.strip()
            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault('rows', 4)


class LoginForm(StyledFormMixin, AuthenticationForm):
    username = forms.CharField(label='Логин')
    password = forms.CharField(label='Пароль', widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()


class DateInput(forms.DateInput):
    input_type = 'date'

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('format', '%Y-%m-%d')
        super().__init__(*args, **kwargs)


class DateTimeInput(forms.DateTimeInput):
    input_type = 'datetime-local'

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('format', '%Y-%m-%dT%H:%M')
        super().__init__(*args, **kwargs)


class DecimalNumberInput(forms.NumberInput):
    input_type = 'number'

    def __init__(self, *args, **kwargs):
        attrs = kwargs.setdefault('attrs', {})
        attrs.setdefault('min', '0')
        attrs.setdefault('step', '0.01')
        super().__init__(*args, **kwargs)


class PositiveIntegerInput(forms.NumberInput):
    input_type = 'number'

    def __init__(self, *args, **kwargs):
        attrs = kwargs.setdefault('attrs', {})
        attrs.setdefault('min', '1')
        attrs.setdefault('step', '1')
        super().__init__(*args, **kwargs)


class BaseModelForm(StyledFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field, forms.DateTimeField):
                field.input_formats = ['%Y-%m-%dT%H:%M']
            elif isinstance(field, forms.DateField):
                field.input_formats = ['%Y-%m-%d', '%d.%m.%Y', '%d.%m.%y']
        self._apply_bootstrap()


class ClientForm(BaseModelForm):
    class Meta:
        model = Client
        fields = ['name', 'phone', 'email', 'address', 'notes']


class DriverForm(BaseModelForm):
    class Meta:
        model = Driver
        fields = ['full_name', 'phone', 'license_number', 'notes']


class VehicleForm(BaseModelForm):
    class Meta:
        model = Vehicle
        fields = ['registration_number', 'brand', 'model', 'capacity_tons', 'notes']


class TransportationRequestForm(BaseModelForm):
    COST_SOURCE_FIELDS = {'cargo_type', 'cargo_weight', 'cargo_volume'}

    class Meta:
        model = TransportationRequest
        fields = [
            'client',
            'cargo_type',
            'cargo_name',
            'cargo_weight',
            'cargo_volume',
            'route_from',
            'route_to',
            'transportation_date',
            'cost',
            'status',
            'comment',
        ]
        widgets = {
            'transportation_date': DateInput(),
            'comment': forms.Textarea(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initial_calculated_cost = None
        if self.instance and self.instance.pk:
            self._initial_calculated_cost = self.instance.calculate_cost()

        self.fields['status'].queryset = RequestStatus.objects.order_by('order', 'name')
        self.fields['cargo_type'].help_text = 'Тип груза влияет на автоматический расчет стоимости: у песка, щебня и бетона разные тарифы.'
        self.fields['cost'].required = False
        self.fields['cost'].help_text = 'Можно оставить пустым: система рассчитает стоимость автоматически по типу груза, массе или объему. При изменении типа груза, массы или объема стоимость пересчитается, если вы не вводили ее вручную.'
        self.fields['cost'].widget.attrs.setdefault('placeholder', 'Рассчитается автоматически')

    def _should_recalculate_existing_cost(self):
        if not self.instance or not self.instance.pk:
            return False
        if 'cost' in self.changed_data:
            return False
        if not self.COST_SOURCE_FIELDS.intersection(self.changed_data):
            return False
        return self.instance.cost == self._initial_calculated_cost

    def save(self, commit=True):
        request_obj = super().save(commit=False)
        if self._should_recalculate_existing_cost():
            calculated_cost = request_obj.calculate_cost()
            if calculated_cost is not None:
                request_obj.cost = calculated_cost
                request_obj._cost_was_auto_calculated = True

        if commit:
            request_obj.save()
            self.save_m2m()
        return request_obj


class TransportationAssignForm(BaseModelForm):
    class Meta:
        model = Transportation
        fields = [
            'vehicle',
            'driver',
            'trip_count',
            'distance_parking_to_loading_km',
            'distance_loading_to_customer_km',
            'distance_customer_to_loading_km',
            'assigned_at',
            'departure_at',
            'arrival_at',
            'notes',
        ]
        widgets = {
            'trip_count': PositiveIntegerInput(),
            'distance_parking_to_loading_km': DecimalNumberInput(),
            'distance_loading_to_customer_km': DecimalNumberInput(),
            'distance_customer_to_loading_km': DecimalNumberInput(),
            'assigned_at': DateTimeInput(),
            'departure_at': DateTimeInput(),
            'arrival_at': DateTimeInput(),
            'notes': forms.Textarea(),
        }

    def __init__(self, *args, **kwargs):
        self.request_obj = kwargs.pop('request_obj', None)
        super().__init__(*args, **kwargs)
        if self.request_obj is None and self.instance and self.instance.pk:
            self.request_obj = self.instance.request

        self.load_percent_preview = None
        self.required_trip_count_preview = None
        self.total_distance_preview = None
        self.distance_cost_preview = None
        current_vehicle_ids = {self.instance.vehicle_id} if self.instance and self.instance.pk else set()
        current_driver_ids = {self.instance.driver_id} if self.instance and self.instance.pk else set()

        if self.is_bound:
            bound_vehicle_id = self.data.get('vehicle')
            bound_driver_id = self.data.get('driver')
            if bound_vehicle_id:
                current_vehicle_ids.add(bound_vehicle_id)
            if bound_driver_id:
                current_driver_ids.add(bound_driver_id)

        self.fields['vehicle'].queryset = Vehicle.objects.filter(Q(is_available=True) | Q(pk__in=current_vehicle_ids)).distinct()
        self.fields['driver'].queryset = Driver.objects.filter(Q(is_available=True) | Q(pk__in=current_driver_ids)).distinct()
        self.fields['vehicle'].help_text = 'Если в заявке указана масса, система проверит суммарную грузоподъемность выбранного транспорта за указанное число рейсов.'
        self.fields['trip_count'].help_text = 'Укажите, сколько доставок сделает это ТС в рамках одной заявки.'
        self.fields['distance_parking_to_loading_km'].help_text = 'Плечо 1: от стоянки транспорта до места погрузки.'
        self.fields['distance_loading_to_customer_km'].help_text = 'Плечо 2: от места погрузки до заказчика. Умножается на количество рейсов.'
        self.fields['distance_customer_to_loading_km'].help_text = 'Плечо 3: возврат от заказчика к месту погрузки между повторными рейсами.'
        self._set_load_preview()
        self._set_distance_preview()

    def _set_load_preview(self):
        if not self.request_obj or self.request_obj.cargo_weight is None:
            return

        vehicle_id = None
        if self.is_bound:
            vehicle_id = self.data.get('vehicle')
        elif self.instance and self.instance.vehicle_id:
            vehicle_id = self.instance.vehicle_id

        if not vehicle_id:
            return

        vehicle = Vehicle.objects.filter(pk=vehicle_id).first()
        if not vehicle or not vehicle.capacity_tons:
            return

        trip_count = self._get_trip_count_value()
        self.required_trip_count_preview = int(
            (self.request_obj.cargo_weight / vehicle.capacity_tons).to_integral_value(rounding=ROUND_CEILING)
        )
        total_capacity = vehicle.capacity_tons * trip_count
        if not total_capacity:
            return

        self.load_percent_preview = (
            self.request_obj.cargo_weight / total_capacity * Decimal('100')
        ).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)

    def _get_trip_count_value(self):
        raw_value = self.data.get('trip_count') if self.is_bound else getattr(self.instance, 'trip_count', None)
        try:
            return max(int(raw_value or 1), 1)
        except (TypeError, ValueError):
            return 1

    def _get_decimal_value(self, field_name):
        raw_value = self.data.get(field_name) if self.is_bound else getattr(self.instance, field_name, None)
        try:
            return Decimal(str(raw_value or 0))
        except (TypeError, ValueError):
            return Decimal('0')

    def _set_distance_preview(self):
        trip_count = self._get_trip_count_value()
        parking_to_loading = self._get_decimal_value('distance_parking_to_loading_km')
        loading_to_customer = self._get_decimal_value('distance_loading_to_customer_km')
        customer_to_loading = self._get_decimal_value('distance_customer_to_loading_km')
        return_trip_count = max(trip_count - 1, 0)
        total_distance = (
            parking_to_loading
            + loading_to_customer * trip_count
            + customer_to_loading * return_trip_count
        ).quantize(Decimal('0.01'))

        if total_distance:
            self.total_distance_preview = total_distance
            self.distance_cost_preview = (
                total_distance * TransportationRequest.DISTANCE_RATE_PER_KM
            ).quantize(Decimal('0.01'))

    def clean(self):
        cleaned_data = super().clean()
        vehicle = cleaned_data.get('vehicle')
        trip_count = cleaned_data.get('trip_count') or 1
        if self.request_obj and vehicle and self.request_obj.cargo_weight is not None:
            total_capacity = vehicle.capacity_tons * trip_count if vehicle.capacity_tons else None
            if total_capacity and self.request_obj.cargo_weight > total_capacity:
                required_trips = int(
                    (self.request_obj.cargo_weight / vehicle.capacity_tons).to_integral_value(rounding=ROUND_CEILING)
                )
                self.add_error('trip_count', f'Для этой массы груза нужно минимум {required_trips} рейс(ов) выбранного транспорта.')
        return cleaned_data
