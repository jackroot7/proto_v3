from django.urls import path
from . import views

app_name = 'settings'

urlpatterns = [
    path('', views.settings_index, name='index'),
    path('language/', views.change_language, name='change_language'),
]
