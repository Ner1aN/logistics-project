from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Avg, Count, Prefetch, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import ClientForm, DriverForm, TransportationAssignForm, TransportationRequestForm, VehicleForm
from .pdf import build_reports_pdf
from .models import (
    Client,
    Driver,
    RequestStatus,
    RequestStatusHistory,
    Transportation,
    TransportationRequest,
    Vehicle,
    ensure_default_statuses,
)


class BaseSuccessMessageMixin:
    success_message = 'Данные сохранены.'

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, self.success_message)
        return response


def _filter_requests(queryset, params, archive_mode=None):
    status_code = params.get('status', '').strip()
    client_id = params.get('client', '').strip()
    cargo_type = params.get('cargo_type', '').strip()
    route = params.get('route', '').strip()
    date_from = params.get('date_from', '').strip()
    date_to = params.get('date_to', '').strip()

    if status_code:
        queryset = queryset.filter(status__code=status_code)
    if client_id:
        queryset = queryset.filter(client_id=client_id)
    if cargo_type:
        queryset = queryset.filter(cargo_type=cargo_type)
    if route:
        queryset = queryset.filter(Q(route_from__icontains=route) | Q(route_to__icontains=route))
    if date_from:
        queryset = queryset.filter(transportation_date__gte=date_from)
    if date_to:
        queryset = queryset.filter(transportation_date__lte=date_to)

    if archive_mode is True:
        queryset = queryset.filter(archived=True)
    elif archive_mode is False:
        queryset = queryset.filter(archived=False)

    return queryset


@login_required
def dashboard(request):
    ensure_default_statuses()
    today = timezone.localdate()
    request_queryset = TransportationRequest.objects.select_related('client', 'status', 'transportation__driver', 'transportation__vehicle')
    upcoming_transportations = (
        Transportation.objects.select_related('request', 'request__client', 'driver', 'vehicle')
        .filter(request__transportation_date__gte=today)
        .exclude(request__status__code='cancelled')
        .order_by('request__transportation_date', 'assigned_at')[:6]
    )
    context = {
        'new_count': request_queryset.filter(status__code='new', archived=False).count(),
        'active_count': request_queryset.filter(status__code__in=['processing', 'assigned', 'in_progress'], archived=False).count(),
        'completed_count': request_queryset.filter(status__code='completed').count(),
        'cancelled_count': request_queryset.filter(status__code='cancelled').count(),
        'available_vehicles': Vehicle.objects.filter(is_available=True).count(),
        'available_drivers': Driver.objects.filter(is_available=True).count(),
        'latest_requests': request_queryset.order_by('-created_at')[:6],
        'upcoming_transportations': upcoming_transportations,
    }
    return render(request, 'logistics/dashboard.html', context)


class ClientListView(LoginRequiredMixin, ListView):
    model = Client
    template_name = 'logistics/client_list.html'
    context_object_name = 'clients'

    def get_queryset(self):
        query = self.request.GET.get('q', '').strip()
        queryset = Client.objects.all()
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(phone__icontains=query) | Q(email__icontains=query))
        return queryset


class ClientCreateView(LoginRequiredMixin, BaseSuccessMessageMixin, CreateView):
    model = Client
    form_class = ClientForm
    template_name = 'logistics/form.html'
    success_url = reverse_lazy('client-list')
    success_message = 'Клиент успешно добавлен.'


class ClientUpdateView(LoginRequiredMixin, BaseSuccessMessageMixin, UpdateView):
    model = Client
    form_class = ClientForm
    template_name = 'logistics/form.html'
    success_url = reverse_lazy('client-list')
    success_message = 'Данные клиента обновлены.'


class DriverListView(LoginRequiredMixin, ListView):
    model = Driver
    template_name = 'logistics/driver_list.html'
    context_object_name = 'drivers'

    def get_queryset(self):
        query = self.request.GET.get('q', '').strip()
        availability = self.request.GET.get('availability', '').strip()
        queryset = Driver.objects.all()
        if query:
            queryset = queryset.filter(Q(full_name__icontains=query) | Q(phone__icontains=query) | Q(license_number__icontains=query))
        if availability == 'free':
            queryset = queryset.filter(is_available=True)
        elif availability == 'busy':
            queryset = queryset.filter(is_available=False)
        return queryset


class DriverCreateView(LoginRequiredMixin, BaseSuccessMessageMixin, CreateView):
    model = Driver
    form_class = DriverForm
    template_name = 'logistics/form.html'
    success_url = reverse_lazy('driver-list')
    success_message = 'Водитель успешно добавлен.'


class DriverUpdateView(LoginRequiredMixin, BaseSuccessMessageMixin, UpdateView):
    model = Driver
    form_class = DriverForm
    template_name = 'logistics/form.html'
    success_url = reverse_lazy('driver-list')
    success_message = 'Данные водителя обновлены.'


class VehicleListView(LoginRequiredMixin, ListView):
    model = Vehicle
    template_name = 'logistics/vehicle_list.html'
    context_object_name = 'vehicles'

    def get_queryset(self):
        query = self.request.GET.get('q', '').strip()
        availability = self.request.GET.get('availability', '').strip()
        queryset = Vehicle.objects.all()
        if query:
            queryset = queryset.filter(Q(registration_number__icontains=query) | Q(brand__icontains=query) | Q(model__icontains=query))
        if availability == 'free':
            queryset = queryset.filter(is_available=True)
        elif availability == 'busy':
            queryset = queryset.filter(is_available=False)
        return queryset


class VehicleCreateView(LoginRequiredMixin, BaseSuccessMessageMixin, CreateView):
    model = Vehicle
    form_class = VehicleForm
    template_name = 'logistics/form.html'
    success_url = reverse_lazy('vehicle-list')
    success_message = 'Транспортное средство добавлено.'


class VehicleUpdateView(LoginRequiredMixin, BaseSuccessMessageMixin, UpdateView):
    model = Vehicle
    form_class = VehicleForm
    template_name = 'logistics/form.html'
    success_url = reverse_lazy('vehicle-list')
    success_message = 'Данные транспортного средства обновлены.'


class RequestListView(LoginRequiredMixin, ListView):
    model = TransportationRequest
    template_name = 'logistics/request_list.html'
    context_object_name = 'requests'
    archive_mode = False
    page_title = 'Активные заявки'
    page_description = 'Текущие перевозки, назначения и работа менеджера по логистике.'

    def get_queryset(self):
        queryset = TransportationRequest.objects.select_related(
            'client',
            'status',
            'transportation__driver',
            'transportation__vehicle',
        )
        queryset = _filter_requests(queryset, self.request.GET, archive_mode=self.archive_mode)
        if self.archive_mode:
            return queryset.order_by('-transportation_date', '-updated_at')
        return queryset.order_by('transportation_date', 'created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['statuses'] = RequestStatus.objects.all()
        context['clients'] = Client.objects.all()
        context['cargo_types'] = TransportationRequest.CargoType.choices
        context['archive_mode'] = self.archive_mode
        context['title'] = self.page_title
        context['description'] = self.page_description
        return context


class ArchivedRequestListView(RequestListView):
    archive_mode = True
    page_title = 'Архив заявок'
    page_description = 'Завершенные, отмененные и вручную архивированные заявки.'


class RequestDetailView(LoginRequiredMixin, DetailView):
    model = TransportationRequest
    template_name = 'logistics/request_detail.html'
    context_object_name = 'request_obj'

    def get_queryset(self):
        return TransportationRequest.objects.select_related(
            'client',
            'status',
            'created_by',
            'transportation__driver',
            'transportation__vehicle',
        ).prefetch_related(
            Prefetch(
                'status_history',
                queryset=RequestStatusHistory.objects.select_related('status', 'changed_by'),
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['transportation'] = getattr(self.object, 'transportation', None)
        context['can_assign'] = not self.object.archived and not self.object.is_terminal
        return context


class RequestCreateView(LoginRequiredMixin, BaseSuccessMessageMixin, CreateView):
    model = TransportationRequest
    form_class = TransportationRequestForm
    template_name = 'logistics/form.html'
    success_message = 'Заявка успешно создана.'

    def form_valid(self, form):
        cost_was_blank = form.cleaned_data.get('cost') is None
        form.instance.created_by = self.request.user
        form.instance._status_changed_by = self.request.user
        response = super().form_valid(form)
        if cost_was_blank and getattr(self.object, '_cost_was_auto_calculated', False):
            messages.info(self.request, f'Стоимость рассчитана автоматически: {self.object.cost} ₽.')
        return response

    def get_success_url(self):
        return reverse('request-detail', kwargs={'pk': self.object.pk})


class RequestUpdateView(LoginRequiredMixin, BaseSuccessMessageMixin, UpdateView):
    model = TransportationRequest
    form_class = TransportationRequestForm
    template_name = 'logistics/form.html'
    success_message = 'Заявка обновлена.'

    def form_valid(self, form):
        cost_was_blank = form.cleaned_data.get('cost') is None
        form.instance._status_changed_by = self.request.user
        response = super().form_valid(form)
        if cost_was_blank and getattr(self.object, '_cost_was_auto_calculated', False):
            messages.info(self.request, f'Стоимость рассчитана автоматически: {self.object.cost} ₽.')
        return response

    def get_success_url(self):
        return reverse('request-detail', kwargs={'pk': self.object.pk})


class TransportationListView(LoginRequiredMixin, ListView):
    model = Transportation
    template_name = 'logistics/transportation_list.html'
    context_object_name = 'transportations'

    def get_queryset(self):
        query = self.request.GET.get('q', '').strip()
        date_from = self.request.GET.get('date_from', '').strip()
        date_to = self.request.GET.get('date_to', '').strip()
        queryset = Transportation.objects.select_related('request', 'request__client', 'request__status', 'driver', 'vehicle')
        if query:
            queryset = queryset.filter(
                Q(request__client__name__icontains=query)
                | Q(driver__full_name__icontains=query)
                | Q(vehicle__registration_number__icontains=query)
                | Q(request__route_from__icontains=query)
                | Q(request__route_to__icontains=query)
            )
        if date_from:
            queryset = queryset.filter(request__transportation_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(request__transportation_date__lte=date_to)
        return queryset.order_by('request__transportation_date', 'assigned_at')


class TransportationDetailView(LoginRequiredMixin, DetailView):
    model = Transportation
    template_name = 'logistics/transportation_detail.html'
    context_object_name = 'transportation'

    def get_queryset(self):
        return Transportation.objects.select_related('request', 'request__client', 'request__status', 'driver', 'vehicle')


@login_required
def assign_transportation(request, pk):
    request_obj = get_object_or_404(
        TransportationRequest.objects.select_related('client', 'status', 'transportation__driver', 'transportation__vehicle'),
        pk=pk,
    )
    instance = getattr(request_obj, 'transportation', None)
    form = TransportationAssignForm(request.POST or None, instance=instance, request_obj=request_obj)
    if request.method == 'POST' and form.is_valid():
        transportation = form.save(commit=False)
        transportation.request = request_obj
        transportation._acting_user = request.user
        transportation.save()
        messages.success(request, 'Водитель и транспорт закреплены за заявкой.')
        return redirect('request-detail', pk=request_obj.pk)
    return render(
        request,
        'logistics/form.html',
        {
            'form': form,
            'object': request_obj,
            'title': f'Назначение перевозки для заявки #{request_obj.pk}',
        },
    )


@login_required
@require_POST
def toggle_archive_request(request, pk):
    request_obj = get_object_or_404(TransportationRequest, pk=pk)
    if request_obj.is_terminal and request_obj.archived:
        messages.error(request, 'Завершенные и отмененные заявки остаются в архиве.')
        return redirect('request-detail', pk=request_obj.pk)

    request_obj.archived = not request_obj.archived
    request_obj.save(update_fields=['archived', 'updated_at'])
    messages.success(request, 'Статус архива для заявки изменен.')
    return redirect('request-detail', pk=request_obj.pk)


def _build_reports_context(params):
    ensure_default_statuses()
    request_queryset = TransportationRequest.objects.select_related(
        'client',
        'status',
        'transportation__driver',
        'transportation__vehicle',
    )
    request_queryset = _filter_requests(request_queryset, params, archive_mode=None)

    completed_transportations = Transportation.objects.select_related(
        'request',
        'request__client',
        'request__status',
        'driver',
        'vehicle',
    ).filter(request__status__code='completed')

    client_id = params.get('client', '').strip()
    cargo_type = params.get('cargo_type', '').strip()
    date_from = params.get('date_from', '').strip()
    date_to = params.get('date_to', '').strip()

    if client_id:
        completed_transportations = completed_transportations.filter(request__client_id=client_id)
    if cargo_type:
        completed_transportations = completed_transportations.filter(request__cargo_type=cargo_type)
    if date_from:
        completed_transportations = completed_transportations.filter(request__transportation_date__gte=date_from)
    if date_to:
        completed_transportations = completed_transportations.filter(request__transportation_date__lte=date_to)

    status_stats = request_queryset.values('status__name', 'status__code').annotate(
        total=Count('id'),
        total_cost=Sum('cost'),
    ).order_by('status__name')

    today = timezone.localdate()
    request_total_count = request_queryset.count()
    completed_request_count = request_queryset.filter(status__code='completed').count()
    overdue_request_count = (
        request_queryset
        .filter(transportation_date__lt=today)
        .exclude(status__code__in=TransportationRequest.TERMINAL_STATUS_CODES)
        .count()
    )
    active_request_count = (
        request_queryset
        .exclude(status__code__in=TransportationRequest.TERMINAL_STATUS_CODES)
        .filter(transportation_date__gte=today)
        .count()
    )
    average_request_cost = request_queryset.aggregate(avg=Avg('cost'))['avg'] or 0
    completed_request_percent = round(completed_request_count / request_total_count * 100, 1) if request_total_count else 0

    driver_load_stats = completed_transportations.values('driver__full_name').annotate(
        total=Count('id'),
    ).order_by('-total', 'driver__full_name')

    driver_load_chart = [
        {
            'label': row['driver__full_name'],
            'count': row['total'],
        }
        for row in driver_load_stats
    ]

    status_chart = [
        {
            'label': row['status__name'],
            'count': row['total'],
            'cost': float(row['total_cost'] or 0),
        }
        for row in status_stats
    ]

    request_dynamics_chart = [
        {
            'label': row['transportation_date'].strftime('%d.%m.%Y'),
            'count': row['total'],
            'cost': float(row['total_cost'] or 0),
        }
        for row in request_queryset.values('transportation_date').annotate(
            total=Count('id'),
            total_cost=Sum('cost'),
        ).order_by('transportation_date')
        if row['transportation_date']
    ]

    completed_dynamics_chart = [
        {
            'label': row['request__transportation_date'].strftime('%d.%m.%Y'),
            'count': row['total'],
        }
        for row in completed_transportations.values('request__transportation_date').annotate(
            total=Count('id'),
        ).order_by('request__transportation_date')
        if row['request__transportation_date']
    ]

    return {
        'statuses': RequestStatus.objects.all(),
        'clients': Client.objects.all(),
        'cargo_types': TransportationRequest.CargoType.choices,
        'request_total_cost': request_queryset.aggregate(total=Sum('cost'))['total'] or 0,
        'request_total_count': request_total_count,
        'completed_transportation_count': completed_transportations.count(),
        'completed_transportation_cost': completed_transportations.aggregate(total=Sum('request__cost'))['total'] or 0,
        'average_request_cost': average_request_cost,
        'completed_request_percent': completed_request_percent,
        'overdue_request_count': overdue_request_count,
        'active_request_count': active_request_count,
        'completed_request_count': completed_request_count,
        'driver_load_stats': driver_load_stats,
        'driver_load_chart': driver_load_chart,
        'status_stats': status_stats,
        'status_chart': status_chart,
        'request_dynamics_chart': request_dynamics_chart,
        'completed_dynamics_chart': completed_dynamics_chart,
        'requests': request_queryset.order_by('-transportation_date', '-created_at')[:25],
        'completed_transportations': completed_transportations.order_by('-request__transportation_date', '-assigned_at')[:25],
    }


@login_required
def reports_view(request):
    context = _build_reports_context(request.GET)
    return render(request, 'logistics/reports.html', context)


@login_required
def reports_pdf_view(request):
    context = _build_reports_context(request.GET)
    pdf = build_reports_pdf(context, request.GET)
    filename = timezone.localdate().strftime('logistics_report_%Y_%m_%d.pdf')
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

