from django.urls import path
from .views import WebhookView, health_view

urlpatterns = [
    path("health/", health_view, name="health"),
    path("webhook/<str:token>/", WebhookView.as_view(), name="webhook"),
]
