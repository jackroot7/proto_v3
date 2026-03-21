from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('shop-select/', views.shop_select, name='shop_select'),
    path('switch-shop/', views.switch_shop, name='switch_shop'),
    path('day/open/', views.open_day, name='open_day'),
    path('day/close/', views.close_day, name='close_day'),
    path('day/summary/', views.day_summary, name='day_summary'),
]
