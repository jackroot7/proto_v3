from django.contrib import admin
from .models import Motorcycle, Driver, DeliveryOrder, DeliveryStop, DeliveryStopItem


class DeliveryStopItemInline(admin.TabularInline):
    model = DeliveryStopItem
    extra = 0


class DeliveryStopInline(admin.StackedInline):
    model = DeliveryStop
    extra = 0
    show_change_link = True


@admin.register(Motorcycle)
class MotorcycleAdmin(admin.ModelAdmin):
    list_display = ['plate_number', 'make', 'model', 'color', 'shop', 'status']
    list_filter = ['shop', 'status']


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'shop', 'motorcycle', 'is_active']
    list_filter = ['shop', 'is_active']


@admin.register(DeliveryOrder)
class DeliveryOrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'shop', 'driver', 'status', 'total', 'created_at']
    list_filter = ['shop', 'status', 'driver']
    inlines = [DeliveryStopInline]


@admin.register(DeliveryStop)
class DeliveryStopAdmin(admin.ModelAdmin):
    list_display = ['order', 'sequence', 'customer_name', 'delivery_address', 'subtotal']
    inlines = [DeliveryStopItemInline]
