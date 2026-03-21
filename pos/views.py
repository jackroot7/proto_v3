from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
import json

from shops.models import Shop, DaySession
from products.models import Product, ProductVariant, Category
from customers.models import Customer
from stock.models import StockLevel, StockMovement
from .models import Sale, SaleItem


def get_current_shop(request):
    shop_id = request.session.get('current_shop_id')
    if not shop_id:
        return None
    return Shop.objects.filter(id=shop_id).first()


@login_required
def pos_index(request):
    shop = get_current_shop(request)
    if not shop:
        return redirect('shop_select')

    today = timezone.now().date()
    day_session = DaySession.objects.filter(shop=shop, date=today).first()
    categories = Category.objects.filter(shop=shop, is_active=True)

    # Load products with stock for this shop
    products = Product.objects.filter(
        shop=shop, is_active=True
    ).select_related('category').prefetch_related('variants', 'stock_levels')

    cat_filter = request.GET.get('category', '')
    search = request.GET.get('q', '')
    if cat_filter:
        products = products.filter(category__slug=cat_filter)
    if search:
        products = products.filter(name__icontains=search)

    # Annotate each product with its current stock level
    product_data = []
    for p in products:
        stock = StockLevel.objects.filter(product=p, shop=shop).first()
        qty = stock.quantity if stock else 0
        product_data.append({
            'product': p,
            'stock': qty,
            'is_low': qty <= p.low_stock_threshold,
            'is_critical': qty <= 3,
        })

    customers = Customer.objects.filter(shop=shop, is_active=True).order_by('name')

    # Load shop settings for POS enforcement
    from settings_app.models import ShopSettings
    shop_settings, _ = ShopSettings.objects.get_or_create(
        shop=shop,
        defaults={'tax_rate': 18.00, 'low_stock_threshold': 10}
    )

    return render(request, 'pos/index.html', {
        'shop': shop,
        'day_session': day_session,
        'categories': categories,
        'product_data': product_data,
        'customers': customers,
        'selected_category': cat_filter,
        'search': search,
        'shop_settings': shop_settings,
    })


@login_required
@require_POST
def process_sale(request):
    """Ajax endpoint - processes a complete sale transaction."""
    shop = get_current_shop(request)
    if not shop:
        return JsonResponse({'success': False, 'error': 'No shop selected'}, status=400)

    today = timezone.now().date()
    day_session = DaySession.objects.filter(shop=shop, date=today, status='open').first()
    if not day_session:
        return JsonResponse({'success': False, 'error': 'Day is not open. Please open the day first.'}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid data'}, status=400)

    items = data.get('items', [])
    if not items:
        return JsonResponse({'success': False, 'error': 'Cart is empty'}, status=400)

    payment_method = data.get('payment_method', 'cash')
    customer_id = data.get('customer_id')
    amount_paid = Decimal(str(data.get('amount_paid', 0)))

    # Load shop settings for enforcement
    from django.conf import settings as django_settings
    from settings_app.models import ShopSettings
    shop_settings, _ = ShopSettings.objects.get_or_create(shop=shop, defaults={'tax_rate': 18.00})
    allow_negative_stock    = shop_settings.allow_negative_stock
    require_customer_credit = shop_settings.require_customer_on_credit
    TAX_RATE = Decimal(str(shop_settings.tax_rate / 100)) if shop_settings.tax_rate else Decimal(str(getattr(django_settings, 'PROTO_TAX_RATE', 0.18)))

    # Enforce: credit sales require a customer
    if payment_method == 'credit' and require_customer_credit and not customer_id:
        return JsonResponse({
            'success': False,
            'error': 'A customer must be selected for credit sales. Please select or add a customer.'
        }, status=400)

    with transaction.atomic():
        # Validate stock and calculate totals
        sale_items = []
        subtotal = Decimal('0')

        for item_data in items:
            product = get_object_or_404(Product, id=item_data['product_id'], shop=shop)
            variant = None
            if item_data.get('variant_id'):
                variant = get_object_or_404(ProductVariant, id=item_data['variant_id'])

            qty = int(item_data['quantity'])
            unit_price = variant.effective_selling_price if variant else product.selling_price
            buying_price = variant.effective_buying_price if variant else product.buying_price

            # Check stock
            if product.track_stock and not allow_negative_stock:
                stock_level = StockLevel.objects.select_for_update().filter(
                    product=product, variant=variant, shop=shop
                ).first()
                if not stock_level or stock_level.quantity < qty:
                    avail = stock_level.quantity if stock_level else 0
                    return JsonResponse({
                        'success': False,
                        'error': f'Insufficient stock for {product.name}. Available: {avail}'
                    }, status=400)

            line_total = unit_price * qty
            subtotal += line_total
            sale_items.append({
                'product': product,
                'variant': variant,
                'quantity': qty,
                'unit_price': unit_price,
                'buying_price': buying_price,
                'line_total': line_total,
            })

        tax_amount = subtotal * TAX_RATE
        total = subtotal + tax_amount
        change = amount_paid - total if payment_method == 'cash' else Decimal('0')

        # Create the sale
        customer = Customer.objects.filter(id=customer_id, shop=shop).first() if customer_id else None
        sale = Sale.objects.create(
            shop=shop,
            day_session=day_session,
            customer=customer,
            cashier=request.user,
            subtotal=subtotal,
            tax_amount=tax_amount,
            total=total,
            payment_method=payment_method,
            amount_paid=amount_paid,
            change_given=max(change, Decimal('0')),
            status='completed',
        )

        # Create sale items and deduct stock
        for item in sale_items:
            SaleItem.objects.create(
                sale=sale,
                product=item['product'],
                variant=item['variant'],
                quantity=item['quantity'],
                unit_price=item['unit_price'],
                buying_price=item['buying_price'],
                line_total=item['line_total'],
            )

            if item['product'].track_stock:
                sl = StockLevel.objects.select_for_update().get(
                    product=item['product'],
                    variant=item['variant'],
                    shop=shop,
                )
                qty_before = sl.quantity
                sl.quantity -= item['quantity']
                sl.save()

                StockMovement.objects.create(
                    product=item['product'],
                    variant=item['variant'],
                    shop=shop,
                    movement_type='sale',
                    quantity=-item['quantity'],
                    quantity_before=qty_before,
                    quantity_after=sl.quantity,
                    reference=sale.sale_number,
                    created_by=request.user,
                )

        # Handle credit - update customer balance
        if payment_method == 'credit' and customer:
            customer.credit_balance += total
            customer.save(update_fields=['credit_balance'])

        # Queue for sync
        from sync_engine.utils import queue_for_sync
        queue_for_sync(sale, 'create')

    return JsonResponse({
        'success': True,
        'sale_number': sale.sale_number,
        'sale_id': sale.id,
        'total': float(sale.total),
        'amount_paid': float(sale.amount_paid),
        'change': float(sale.change_given),
        'message': f'Sale {sale.sale_number} completed successfully.',
    })


@login_required
def sale_receipt(request, sale_id):
    shop = get_current_shop(request)
    sale = get_object_or_404(Sale, id=sale_id, shop=shop)
    return render(request, 'pos/receipt.html', {'sale': sale})


@login_required
def sale_history(request):
    shop = get_current_shop(request)
    if not shop:
        return redirect('shop_select')
    today = timezone.now().date()
    from django.core.paginator import Paginator
    date_filter = request.GET.get('date', str(today))
    try:
        import datetime
        filter_date = datetime.date.fromisoformat(date_filter)
    except Exception:
        filter_date = today
    sales_qs = Sale.objects.filter(shop=shop, created_at__date=filter_date).select_related(
        'customer', 'cashier'
    ).prefetch_related('items').order_by('-created_at')
    paginator = Paginator(sales_qs, 25)
    page_obj  = paginator.get_page(request.GET.get('page'))
    return render(request, 'pos/history.html', {
        'sales': page_obj, 'page_obj': page_obj,
        'shop': shop, 'filter_date': filter_date, 'today': today,
    })


@login_required
@require_POST
def void_sale(request, sale_id):
    shop = get_current_shop(request)
    role = request.session.get('current_role', 'cashier')
    if role == 'cashier':
        return JsonResponse({'success': False, 'error': 'Permission denied. Only admins can void sales.'}, status=403)

    sale = get_object_or_404(Sale, id=sale_id, shop=shop, status='completed')
    with transaction.atomic():
        sale.status = 'voided'
        sale.voided_by = request.user
        sale.void_reason = request.POST.get('reason', '')
        sale.save()

        # Restore stock
        for item in sale.items.all():
            if item.product.track_stock:
                sl, _ = StockLevel.objects.get_or_create(
                    product=item.product, variant=item.variant, shop=shop,
                    defaults={'quantity': 0}
                )
                qty_before = sl.quantity
                sl.quantity += item.quantity
                sl.save()
                StockMovement.objects.create(
                    product=item.product, variant=item.variant, shop=shop,
                    movement_type='return',
                    quantity=item.quantity,
                    quantity_before=qty_before,
                    quantity_after=sl.quantity,
                    reference=f"VOID-{sale.sale_number}",
                    created_by=request.user,
                )

    return JsonResponse({'success': True, 'message': f'Sale {sale.sale_number} voided.'})


@login_required
@require_POST
def quick_add_customer(request):
    """Ajax: create a customer directly from the POS screen."""
    import json as _json
    shop = get_current_shop(request)
    if not shop:
        return JsonResponse({'success': False, 'error': 'No shop selected.'}, status=400)
    try:
        data = _json.loads(request.body)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid data.'}, status=400)

    name = (data.get('name') or '').strip()
    if not name:
        return JsonResponse({'success': False, 'error': 'Customer name is required.'}, status=400)

    from customers.models import Customer
    customer = Customer.objects.create(
        name=name,
        phone=(data.get('phone') or '').strip(),
        notes=(data.get('notes') or '').strip(),
        shop=shop,
    )
    return JsonResponse({
        'success': True,
        'customer_id': customer.id,
        'customer_name': customer.name,
    })
