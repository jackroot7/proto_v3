from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('shops.urls')),
    path('pos/', include('pos.urls')),
    path('products/', include('products.urls')),
    path('stock/', include('stock.urls')),
    path('purchases/', include('purchases.urls')),
    path('expenses/', include('expenses.urls')),
    path('staff/', include('staff.urls')),
    path('customers/', include('customers.urls')),
    path('reports/', include('reports.urls')),
    path('sync/', include('sync_engine.urls')),
    path('settings/', include('settings_app.urls')),
    path('units/', include('units.urls')),
    path('i18n/', include('django.conf.urls.i18n')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
