from django.contrib import admin
from .models import Sale, SaleItem
class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ['sale_number','shop','total','payment_method','status','created_at']
    inlines = [SaleItemInline]