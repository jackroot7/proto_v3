from django.urls import path
from . import views

app_name = 'products'

urlpatterns = [
    path('', views.product_list, name='list'),
    path('create/', views.product_create, name='create'),
    path('<int:pk>/', views.product_detail, name='detail'),
    path('<int:pk>/edit/', views.product_edit, name='edit'),
    path('categories/', views.category_list, name='categories'),
    path('categories/create/', views.category_create, name='category_create'),

    path('bulk-upload/', views.bulk_upload, name='bulk_upload'),
    # Variant management
    path('<int:product_pk>/variants/', views.variant_manager, name='variants'),
    path('<int:product_pk>/variants/add-type/', views.add_variant_type, name='add_variant_type'),
    path('<int:product_pk>/variants/add-value/', views.add_variant_value, name='add_variant_value'),
    path('<int:product_pk>/variants/<int:variant_pk>/edit/', views.edit_variant, name='edit_variant'),
    path('<int:product_pk>/variants/<int:variant_pk>/delete/', views.delete_variant, name='delete_variant'),
    path('<int:product_pk>/variants/delete-type/', views.delete_variant_type, name='delete_variant_type'),
    # Bulk upload
    path('bulk-upload/', views.bulk_upload, name='bulk_upload'),
    path('bulk-upload/template/', views.download_template, name='download_template'),
]
