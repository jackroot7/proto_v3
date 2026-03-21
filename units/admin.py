from django.contrib import admin
from .models import UnitOfMeasure

@admin.register(UnitOfMeasure)
class UOMAdmin(admin.ModelAdmin):
    list_display = ['name', 'short_name', 'allow_decimals', 'is_active', 'sort_order']
    list_editable = ['short_name', 'allow_decimals', 'is_active', 'sort_order']
