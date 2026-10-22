from django.urls import path

from . import views

urlpatterns = [
    path("aps/plan", views.PlanView.as_view()),
    path("aps/replan", views.ReplanView.as_view()),
    path("aps/compare", views.CompareView.as_view()),
    path("aps/plans/<str:plan_id>/decision", views.PlanDecisionView.as_view()),
    path("aps/calendar", views.CalendarView.as_view()),
    path("aps/holidays", views.HolidayView.as_view()),
    path("aps/holidays/<str:day>", views.HolidayView.as_view()),
    path("aps/staffing", views.StaffingView.as_view()),
]
