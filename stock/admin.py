from django.contrib import admin
from .models import StockLevel, StockMovement, StockTake, StockTakeItem
admin.site.register(StockLevel)
admin.site.register(StockMovement)
admin.site.register(StockTake)
admin.site.register(StockTakeItem)