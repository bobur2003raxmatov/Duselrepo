from django.urls import path
from .views import WebhookView

urlpatterns = [
    path("webhook/<str:token>/", WebhookView.as_view(), name="webhook"),
]
