from django.urls import path

from . import views

urlpatterns = [
    path("health", views.HealthView.as_view()),
    path("mes/settings", views.SettingsView.as_view()),
    path("mes/workstations", views.WorkstationListView.as_view()),
    path("mes/station-status", views.StationStatusView.as_view()),
    path("mes/workstations/<str:ws>/board", views.WorkerBoardView.as_view()),
    path("mes/workstations/<str:ws>/scans", views.ScanFeedView.as_view()),
    path("mes/workstations/<str:ws>/<str:action>", views.WorkerActionView.as_view()),
    path("mes/work-orders", views.WorkOrderListView.as_view()),
    path("mes/progress", views.ProgressView.as_view()),
    path("mes/wip", views.WipListView.as_view()),
    path("mes/wip/<str:wip_id>", views.WipEditView.as_view()),
    path("mes/events", views.EventListView.as_view()),
    path("mes/events/<str:event_id>", views.EventEditView.as_view()),
    path("gateway/scans", views.GatewayScanView.as_view()),
    path("gateway/heartbeat", views.GatewayHeartbeatView.as_view()),
]
