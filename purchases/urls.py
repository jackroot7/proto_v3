from django.urls import path
from . import views

app_name = 'purchases'

urlpatterns = [
    path('', views.order_list, name='list'),
    path('create/', views.order_create, name='create'),
    path('<int:pk>/', views.order_detail, name='detail'),
    path('<int:pk>/add-item/', views.add_item, name='add_item'),
    path('<int:pk>/remove-item/<int:item_pk>/', views.remove_item, name='remove_item'),
    path('<int:pk>/confirm/', views.confirm_order, name='confirm'),
    path('<int:pk>/in-transit/', views.mark_in_transit, name='in_transit'),
    path('<int:pk>/arrived/', views.mark_arrived, name='arrived'),
    path('<int:pk>/inspect/', views.inspect_order, name='inspect'),
    path('<int:pk>/cancel/', views.cancel_order, name='cancel'),
    path('suppliers/', views.supplier_list, name='suppliers'),
    path('suppliers/create/', views.supplier_create, name='supplier_create'),
    path('suppliers/<int:pk>/edit/', views.supplier_edit, name='supplier_edit'),
    path('api/product/<int:product_pk>/variants/', views.product_variants_json, name='product_variants_json'),
]
