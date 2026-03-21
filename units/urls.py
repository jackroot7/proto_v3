from django.urls import path
from . import views

app_name = 'units'

urlpatterns = [
    path('', views.uom_list, name='list'),
    path('create/', views.uom_create, name='create'),
    path('<int:pk>/edit/', views.uom_edit, name='edit'),
]
