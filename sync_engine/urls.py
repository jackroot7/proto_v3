from django.urls import path
from . import views

app_name = 'sync_engine'

urlpatterns = [
    path('status/',         views.sync_status,    name='status'),
    path('trigger/',        views.trigger_sync,   name='trigger'),
    path('retry-failed/',   views.retry_failed,   name='retry_failed'),
    path('clear-synced/',   views.clear_synced,   name='clear_synced'),
    path('purge-failed/',   views.purge_failed,   name='purge_failed'),
    path('dashboard/',      views.sync_dashboard, name='dashboard'),
    path('receive/',        views.receive_sync,   name='receive'),
]