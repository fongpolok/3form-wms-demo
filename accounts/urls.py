from django.urls import path

from . import views

urlpatterns = [
    path("auth/login", views.LoginView.as_view()),
    path("auth/worker-login", views.WorkerLoginView.as_view()),
    path("auth/public-demo", views.PublicDemoView.as_view()),
    path("auth/demo-login", views.DemoLoginView.as_view()),
    path("auth/logout", views.LogoutView.as_view()),
    path("auth/me", views.MeView.as_view()),
    path("devices", views.DeviceListView.as_view()),
    path("devices/current", views.CurrentDeviceView.as_view()),
    path("devices/<int:pk>", views.DeviceDetailView.as_view()),
    path("accounts", views.AccountListView.as_view()),
    path("accounts/<int:pk>", views.AccountDetailView.as_view()),
    path("audit", views.AuditListView.as_view()),
]
