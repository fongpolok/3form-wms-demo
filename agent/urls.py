from django.urls import path

from . import views

urlpatterns = [
    path("agent/advice", views.AdviceView.as_view()),
    path("agent/run", views.AdviceRunView.as_view()),
    path("agent/advice/<str:advice_id>/decision", views.AdviceDecisionView.as_view()),
    path("agent/chat", views.ChatView.as_view()),
    path("search", views.SearchView.as_view()),
    path("sop", views.SopView.as_view()),
    path("sop/<str:sop_id>", views.SopDetailView.as_view()),
]
