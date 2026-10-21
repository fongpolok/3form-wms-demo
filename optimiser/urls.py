from django.urls import path

from . import views

urlpatterns = [
    path("integrations/optimiser", views.OptimiserView.as_view()),
    path("integrations/optimiser/test", views.OptimiserTestView.as_view()),
    path("inventory/pick-route", views.PickRouteView.as_view()),
    path("inventory/pick-route/order/<str:wo_id>", views.OrderPickRouteView.as_view()),
]
