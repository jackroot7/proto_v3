from django.contrib import admin
from .models import SyncQueue, SyncLog
admin.site.register(SyncQueue)
admin.site.register(SyncLog)