from django.urls import path

from . import views

urlpatterns = [
    path("inventory/stock", views.StockView.as_view()),
    path("inventory/receive", views.ReceiveView.as_view()),
    path("inventory/shipments", views.ShipView.as_view()),
    path("inventory/pick-preview/<str:goods_code>", views.PickPreviewView.as_view()),
    path("inventory/bins", views.BinsView.as_view()),
    path("inventory/bins/<str:bin_name>/zone", views.BinZoneView.as_view()),
    path("inventory/counts", views.CountView.as_view()),
    path("inventory/counts/<int:pk>/decision", views.CountDecisionView.as_view()),
    path("inventory/products", views.ProductsView.as_view()),
    path("inventory/goods", views.GoodsLookupView.as_view()),
    path("inventory/material-requests", views.MaterialRequestsView.as_view()),
    path("inventory/movements", views.MovementsView.as_view()),
    path("alerts", views.AlertsView.as_view()),
    path("alerts/<int:pk>/ack", views.AlertAckView.as_view()),
    path("settings/industry", views.IndustryView.as_view()),
]
