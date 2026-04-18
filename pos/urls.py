from django.urls import path
from . import views

app_name = 'pos'

urlpatterns = [
    path('', views.pos_index, name='index'),
    path('sale/', views.process_sale, name='process_sale'),
    path('sale/<int:sale_id>/receipt/', views.sale_receipt, name='receipt'),
    path('sale/<int:sale_id>/void/', views.void_sale, name='void_sale'),
    path('sale/<int:sale_id>/return/', views.create_return, name='create_return'),
    path('sale/<int:sale_id>/edit/', views.edit_sale, name='edit_sale'),
    path('history/', views.sale_history, name='history'),
    path('returns/', views.return_history, name='return_history'),
    path('return/<int:return_id>/', views.return_detail, name='return_detail'),
    path('quick-add-customer/', views.quick_add_customer, name='quick_add_customer'),
]
