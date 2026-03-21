from django.urls import path
from . import views

app_name = 'pos'

urlpatterns = [
    path('', views.pos_index, name='index'),
    path('sale/', views.process_sale, name='process_sale'),
    path('sale/<int:sale_id>/receipt/', views.sale_receipt, name='receipt'),
    path('sale/<int:sale_id>/void/', views.void_sale, name='void_sale'),
    path('history/', views.sale_history, name='history'),
    path('quick-add-customer/', views.quick_add_customer, name='quick_add_customer'),
]
