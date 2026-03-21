from django.urls import path
from . import views

app_name = 'stock'

urlpatterns = [
    path('', views.stock_list, name='list'),
    path('adjust/<int:product_pk>/', views.adjust_stock, name='adjust'),
    path('movements/', views.movement_history, name='movements'),
    path('take/', views.stock_take_create, name='take_create'),
    path('take/<int:pk>/', views.stock_take_detail, name='take_detail'),
]
