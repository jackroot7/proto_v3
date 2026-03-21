from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.reports_dashboard, name='dashboard'),
    path('export/pdf/',   views.export_pdf,   name='export_pdf'),
    path('export/csv/',   views.export_csv,   name='export_csv'),
    path('export/excel/', views.export_excel, name='export_excel'),
]
