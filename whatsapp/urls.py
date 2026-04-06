from django.urls import path
from . import views

app_name = 'whatsapp'

urlpatterns = [
    path('test/',                               views.send_test,                       name='test'),
    path('send-custom/',                        views.send_custom,                     name='send_custom'),
    path('low-stock-alert/',                    views.send_low_stock_alert,            name='low_stock_alert'),
    path('credit-reminder/<int:customer_pk>/',  views.send_credit_reminder,            name='credit_reminder'),
    path('receipt/<int:sale_pk>/',              views.send_receipt_to_customer,        name='send_receipt'),
    path('purchase-order/<int:order_pk>/',      views.send_purchase_order_to_supplier, name='purchase_order'),
]