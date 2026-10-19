from django.urls import path

from . import views

urlpatterns = [
    path("integrations/ai", views.AiProviderView.as_view()),
    path("integrations/ai/test", views.AiTestView.as_view()),
    path("integrations/erp", views.ErpView.as_view()),
    path("integrations/erp/<int:pk>", views.ErpView.as_view()),
    path("integrations/erp/<int:pk>/test", views.ErpTestView.as_view()),
    path("integrations/erp-sync", views.ErpSyncView.as_view()),
    path("integrations/erp-inbox", views.ErpInboxView.as_view()),
    path("integrations/api-keys", views.ApiKeysView.as_view()),
    path("integrations/api-keys/<int:pk>/revoke", views.ApiKeyRevokeView.as_view()),
]
