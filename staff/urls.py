from django.urls import path
from . import views

app_name = 'staff'

urlpatterns = [
    path('', views.staff_list, name='list'),
    path('create/', views.staff_create, name='create'),
    path('<int:pk>/', views.staff_detail, name='detail'),
    path('<int:pk>/disciplinary/', views.add_disciplinary, name='disciplinary'),
]
