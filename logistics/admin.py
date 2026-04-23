from django.contrib import admin

from .models import (
    Client,
    Driver,
    Profile,
    RequestStatus,
    RequestStatusHistory,
    Transportation,
    TransportationRequest,
    Vehicle,
)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role')
    list_filter = ('role',)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'email')
    search_fields = ('name', 'phone', 'email')


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'phone', 'license_number', 'is_available')
    list_filter = ('is_available',)
    search_fields = ('full_name', 'phone', 'license_number')
    readonly_fields = ('is_available',)


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ('registration_number', 'brand', 'model', 'capacity_tons', 'is_available')
    list_filter = ('is_available',)
    search_fields = ('registration_number', 'brand', 'model')
    readonly_fields = ('is_available',)


@admin.register(RequestStatus)
class RequestStatusAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'order')
    ordering = ('order',)
    search_fields = ('name', 'code')


class RequestStatusHistoryInline(admin.TabularInline):
    model = RequestStatusHistory
    extra = 0
    can_delete = False
    readonly_fields = ('status', 'changed_at', 'changed_by')


class TransportationInline(admin.StackedInline):
    model = Transportation
    extra = 0


@admin.register(TransportationRequest)
class TransportationRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'cargo_type', 'transportation_date', 'status', 'cost', 'archived')
    list_filter = ('cargo_type', 'status', 'archived', 'transportation_date')
    search_fields = ('client__name', 'route_from', 'route_to', 'cargo_name')
    autocomplete_fields = ('client', 'status', 'created_by')
    inlines = [TransportationInline, RequestStatusHistoryInline]


@admin.register(RequestStatusHistory)
class RequestStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ('request', 'status', 'changed_at', 'changed_by')
    list_filter = ('status', 'changed_at')
    search_fields = ('request__client__name', 'request__route_from', 'request__route_to')
    autocomplete_fields = ('request', 'status', 'changed_by')


@admin.register(Transportation)
class TransportationAdmin(admin.ModelAdmin):
    list_display = ('request', 'vehicle', 'driver', 'assigned_at', 'departure_at', 'arrival_at')
    list_filter = ('assigned_at', 'departure_at', 'arrival_at')
    search_fields = (
        'request__client__name',
        'request__route_from',
        'request__route_to',
        'driver__full_name',
        'vehicle__registration_number',
    )
    autocomplete_fields = ('request', 'vehicle', 'driver')
