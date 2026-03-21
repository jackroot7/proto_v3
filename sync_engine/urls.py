from django.urls import path
from . import views

app_name = 'sync_engine'

urlpatterns = [
    path('status/', views.sync_status, name='status'),
    path('trigger/', views.trigger_sync, name='trigger'),
]
