from decimal import Decimal, ROUND_HALF_UP

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
        self.fields['status'].queryset = RequestStatus.objects.order_by('order', 'name')
        self.fields['cargo_type'].help_text = 'Тип груза влияет на автоматический расчет стоимости: у песка, щебня и бетона разные тарифы.'
        self.fields['cost'].required = False
        self.fields['cost'].help_text = 'Можно оставить пустым: система рассчитает стоимость автоматически по типу груза, массе или объему.'
        self.fields['cost'].widget.attrs.setdefault('placeholder', 'Рассчитается автоматически')


class TransportationAssignForm(BaseModelForm):
    class Meta:
        model = Transportation
        fields = ['vehicle', 'driver', 'assigned_at', 'departure_at', 'arrival_at', 'notes']
        widgets = {
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
        self.fields['vehicle'].help_text = 'Если в заявке указана масса, система проверит грузоподъемность выбранного транспорта.'
        self._set_load_preview()

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

        self.load_percent_preview = (
            self.request_obj.cargo_weight / vehicle.capacity_tons * Decimal('100')
        ).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)

    def clean(self):
        cleaned_data = super().clean()
        vehicle = cleaned_data.get('vehicle')
        if self.request_obj and vehicle and self.request_obj.cargo_weight is not None:
            if vehicle.capacity_tons and self.request_obj.cargo_weight > vehicle.capacity_tons:
                self.add_error('vehicle', 'Выбранное транспортное средство не подходит по грузоподъемности.')
        return cleaned_data
