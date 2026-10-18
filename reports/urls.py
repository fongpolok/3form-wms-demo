from django.urls import path

from . import views

urlpatterns = [
    path("reports/production.xlsx", views.ProductionExcelView.as_view()),
]
