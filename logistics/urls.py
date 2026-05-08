from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from . import views
from .forms import LoginForm

urlpatterns = [
    path('login/', LoginView.as_view(authentication_form=LoginForm, template_name='logistics/login.html'), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('', views.dashboard, name='dashboard'),

    path('clients/', views.ClientListView.as_view(), name='client-list'),
    path('clients/create/', views.ClientCreateView.as_view(), name='client-create'),
    path('clients/<int:pk>/edit/', views.ClientUpdateView.as_view(), name='client-edit'),

    path('drivers/', views.DriverListView.as_view(), name='driver-list'),
    path('drivers/create/', views.DriverCreateView.as_view(), name='driver-create'),
    path('drivers/<int:pk>/edit/', views.DriverUpdateView.as_view(), name='driver-edit'),

    path('vehicles/', views.VehicleListView.as_view(), name='vehicle-list'),
    path('vehicles/create/', views.VehicleCreateView.as_view(), name='vehicle-create'),
    path('vehicles/<int:pk>/edit/', views.VehicleUpdateView.as_view(), name='vehicle-edit'),

    path('requests/', views.RequestListView.as_view(), name='request-list'),
    path('requests/archive/', views.ArchivedRequestListView.as_view(), name='request-archive-list'),
    path('requests/create/', views.RequestCreateView.as_view(), name='request-create'),
    path('requests/<int:pk>/', views.RequestDetailView.as_view(), name='request-detail'),
    path('requests/<int:pk>/edit/', views.RequestUpdateView.as_view(), name='request-edit'),
    path('requests/<int:pk>/assign/', views.assign_transportation, name='request-assign'),
    path('requests/<int:pk>/archive/', views.toggle_archive_request, name='request-archive'),

    path('transportations/', views.TransportationListView.as_view(), name='transportation-list'),
    path('transportations/<int:pk>/', views.TransportationDetailView.as_view(), name='transportation-detail'),

    path('reports/', views.reports_view, name='reports'),
    path('reports/pdf/', views.reports_pdf_view, name='reports-pdf'),
]

