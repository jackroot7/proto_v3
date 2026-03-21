from django.contrib import admin
from .models import Shop, UserShopAccess, DaySession
admin.site.register(Shop)
admin.site.register(UserShopAccess)
admin.site.register(DaySession)