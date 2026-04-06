from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
import json


def get_current_shop(request):
    from shops.models import Shop
    shop_id = request.session.get('current_shop_id')
    return Shop.objects.filter(id=shop_id).first() if shop_id else None


@login_required
@require_POST
def send_test(request):
    from .providers import test_connection
    result = test_connection()
    return JsonResponse(result)


@login_required
@require_POST
def send_credit_reminder(request, customer_pk):
    from customers.models import Customer
    from .providers import send_whatsapp
    from .messages import credit_reminder_message

    shop     = get_current_shop(request)
    customer = get_object_or_404(Customer, pk=customer_pk, shop=shop)

    if not customer.phone:
        return JsonResponse({'success': False, 'error': 'Customer has no phone number.'})
    if customer.credit_balance <= 0:
        return JsonResponse({'success': False, 'error': 'Customer has no outstanding balance.'})

    message, media = credit_reminder_message(customer)
    return JsonResponse(send_whatsapp(customer.phone, message, media))


@login_required
@require_POST
def send_receipt_to_customer(request, sale_pk):
    from pos.models import Sale
    from .providers import send_whatsapp
    from .messages import receipt_message

    shop = get_current_shop(request)
    sale = get_object_or_404(Sale, pk=sale_pk, shop=shop)

    if not sale.customer or not sale.customer.phone:
        return JsonResponse({'success': False,
                             'error': 'Sale has no customer with a phone number.'})

    message, media = receipt_message(sale)
    return JsonResponse(send_whatsapp(sale.customer.phone, message, media))


@login_required
@require_POST
def send_purchase_order_to_supplier(request, order_pk):
    from purchases.models import PurchaseOrder
    from .providers import send_whatsapp
    from .messages import purchase_order_message

    shop  = get_current_shop(request)
    order = get_object_or_404(PurchaseOrder, pk=order_pk, shop=shop)

    if not order.supplier.phone:
        return JsonResponse({'success': False, 'error': 'Supplier has no phone number.'})

    message, media = purchase_order_message(order)
    return JsonResponse(send_whatsapp(order.supplier.phone, message, media))


@login_required
@require_POST
def send_low_stock_alert(request):
    from stock.models import StockLevel
    from django.db.models import F
    from .providers import send_whatsapp
    from .messages import low_stock_message
    from settings_app.models import ShopSettings

    shop = get_current_shop(request)
    if not shop:
        return JsonResponse({'success': False, 'error': 'No shop selected.'})

    settings_obj = ShopSettings.objects.filter(shop=shop).first()
    owner_phone  = settings_obj.daily_report_whatsapp if settings_obj else ''
    if not owner_phone:
        return JsonResponse({'success': False,
                             'error': 'No WhatsApp number set in Settings → Daily Reports.'})

    low_items = StockLevel.objects.filter(
        shop=shop,
        quantity__lte=F('product__low_stock_threshold'),
        quantity__gt=0,
    ).select_related('product', 'product__uom').order_by('quantity')[:10]

    if not low_items:
        return JsonResponse({'success': False, 'error': 'No low stock items found.'})

    message, media = low_stock_message(shop.name, low_items)
    return JsonResponse(send_whatsapp(owner_phone, message, media))


@login_required
@require_POST
def send_custom(request):
    try:
        data    = json.loads(request.body)
        to      = data.get('to', '').strip()
        message = data.get('message', '').strip()
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid JSON.'}, status=400)

    if not to:
        return JsonResponse({'success': False, 'error': 'Phone number is required.'})
    if not message:
        return JsonResponse({'success': False, 'error': 'Message is required.'})

    from .providers import send_whatsapp
    return JsonResponse(send_whatsapp(to, message))