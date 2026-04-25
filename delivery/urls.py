from django.urls import path
from . import views

app_name = 'delivery'

urlpatterns = [
    path('', views.board, name='board'),
    path('order/new/', views.create_order, name='create_order'),
    path('order/save/', views.save_order, name='save_order'),
    path('order/<int:pk>/', views.order_detail, name='order_detail'),
    path('order/<int:pk>/pickup/', views.mark_picked_up, name='mark_picked_up'),
    path('order/<int:pk>/close/', views.close_order, name='close_order'),
    path('order/<int:pk>/cancel/', views.cancel_order, name='cancel_order'),
    path('history/', views.order_history, name='history'),
    path('motorcycles/', views.motorcycles_list, name='motorcycles'),
    path('motorcycles/add/', views.motorcycle_form, name='motorcycle_add'),
    path('motorcycles/<int:pk>/edit/', views.motorcycle_form, name='motorcycle_edit'),
    path('drivers/', views.drivers_list, name='drivers'),
    path('drivers/add/', views.driver_form, name='driver_add'),
    path('drivers/<int:pk>/edit/', views.driver_form, name='driver_edit'),
]
