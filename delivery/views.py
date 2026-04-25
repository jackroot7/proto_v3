from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db import transaction
from django.contrib import messages
from decimal import Decimal
import json

from shops.models import Shop, DaySession
from products.models import Product, ProductVariant, Category, ProductPriceTier
from customers.models import Customer
from stock.models import StockLevel, StockMovement
from pos.models import Sale, SaleItem
from .models import Motorcycle, Driver, DeliveryOrder, DeliveryStop, DeliveryStopItem


def get_current_shop(request):
    shop_id = request.session.get('current_shop_id')
    if not shop_id:
        return None
    return Shop.objects.filter(id=shop_id).first()


# ── Board ────────────────────────────────────────────────────────────────────

@login_required
def board(request):
    shop = get_current_shop(request)
    if not shop:
        return redirect('shop_select')

    drivers = Driver.objects.filter(shop=shop, is_active=True).select_related('motorcycle')

    driver_data = []
    for driver in drivers:
        open_orders = driver.delivery_orders.filter(
            shop=shop
        ).exclude(status__in=['closed', 'cancelled']).prefetch_related('stops')
        driver_data.append({
            'driver': driver,
            'orders': open_orders,
        })

    today = timezone.now().date()
    today_stats = {
        'total': DeliveryOrder.objects.filter(shop=shop, created_at__date=today).count(),
        'pending': DeliveryOrder.objects.filter(shop=shop, created_at__date=today, status='pending').count(),
        'picked_up': DeliveryOrder.objects.filter(shop=shop, created_at__date=today, status='picked_up').count(),
        'closed': DeliveryOrder.objects.filter(shop=shop, created_at__date=today, status='closed').count(),
    }

    return render(request, 'delivery/board.html', {
        'driver_data': driver_data,
        'today_stats': today_stats,
        'shop': shop,
    })


# ── Create Order ─────────────────────────────────────────────────────────────

@login_required
def create_order(request):
    shop = get_current_shop(request)
    if not shop:
        return redirect('shop_select')

    today = timezone.now().date()
    day_session = DaySession.objects.filter(shop=shop, date=today, status='open').first()

    drivers = Driver.objects.filter(shop=shop, is_active=True).select_related('motorcycle')
    categories = Category.objects.filter(shop=shop, is_active=True)
    customers = Customer.objects.filter(shop=shop, is_active=True).order_by('name')

    products = Product.objects.filter(
        shop=shop, is_active=True
    ).select_related('category').prefetch_related('variants', 'stock_levels')

    cat_filter = request.GET.get('category', '')
    search = request.GET.get('q', '')
    if cat_filter:
        products = products.filter(category__slug=cat_filter)
    if search:
        products = products.filter(name__icontains=search)

    product_data = []
    for p in products:
        stock = StockLevel.objects.filter(product=p, shop=shop).first()
        qty = stock.quantity if stock else 0
        product_data.append({'product': p, 'stock': qty})

    all_tiers = ProductPriceTier.objects.filter(product__shop=shop).order_by('-min_quantity')
    product_tiers: dict = {}
    variant_tiers: dict = {}
    for t in all_tiers:
        entry = {'min_qty': t.min_quantity, 'price': float(t.unit_price)}
        if t.variant_id:
            variant_tiers.setdefault(t.variant_id, []).append(entry)
        else:
            product_tiers.setdefault(t.product_id, []).append(entry)

    import json as _json
    return render(request, 'delivery/create_order.html', {
        'shop': shop,
        'day_session': day_session,
        'drivers': drivers,
        'categories': categories,
        'customers': customers,
        'product_data': product_data,
        'selected_category': cat_filter,
        'search': search,
        'product_tiers_json': _json.dumps(product_tiers),
        'variant_tiers_json': _json.dumps(variant_tiers),
    })


@login_required
@require_POST
def save_order(request):
    """Ajax — save a new delivery order with multiple stops."""
    shop = get_current_shop(request)
    if not shop:
        return JsonResponse({'success': False, 'error': 'No shop selected'}, status=400)

    today = timezone.now().date()
    day_session = DaySession.objects.filter(shop=shop, date=today, status='open').first()

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid data'}, status=400)

    driver_id = data.get('driver_id')
    if not driver_id:
        return JsonResponse({'success': False, 'error': 'Please select a driver'}, status=400)

    stops_data = data.get('stops', [])
    if not stops_data or not any(s.get('items') for s in stops_data):
        return JsonResponse({'success': False, 'error': 'Add at least one item to a stop'}, status=400)

    driver = get_object_or_404(Driver, id=driver_id, shop=shop, is_active=True)
    delivery_cost = Decimal(str(data.get('delivery_cost', 0) or 0))

    with transaction.atomic():
        order_subtotal = Decimal('0')
        prepared_stops = []

        for seq, stop_data in enumerate(stops_data, start=1):
            items_data = stop_data.get('items', [])
            if not items_data:
                continue

            customer = Customer.objects.filter(
                id=stop_data.get('customer_id'), shop=shop
            ).first() if stop_data.get('customer_id') else None

            stop_subtotal = Decimal('0')
            prepared_items = []

            for item_data in items_data:
                product = get_object_or_404(Product, id=item_data['product_id'], shop=shop)
                variant = None
                if item_data.get('variant_id'):
                    variant = get_object_or_404(ProductVariant, id=item_data['variant_id'])

                qty = int(item_data['quantity'])
                base_price = variant.effective_selling_price if variant else (product.selling_price or Decimal('0'))
                buying_price = variant.effective_buying_price if variant else (product.buying_price or Decimal('0'))

                tiers = ProductPriceTier.objects.filter(
                    product=product, variant=variant, min_quantity__lte=qty,
                ).order_by('-min_quantity').first()
                if tiers is None and variant:
                    tiers = ProductPriceTier.objects.filter(
                        product=product, variant__isnull=True, min_quantity__lte=qty,
                    ).order_by('-min_quantity').first()
                unit_price = tiers.unit_price if tiers else base_price

                line_total = unit_price * qty
                stop_subtotal += line_total
                prepared_items.append({
                    'product': product,
                    'variant': variant,
                    'quantity': qty,
                    'unit_price': unit_price,
                    'buying_price': buying_price,
                    'line_total': line_total,
                })

            order_subtotal += stop_subtotal
            prepared_stops.append({
                'sequence': seq,
                'customer': customer,
                'customer_name': stop_data.get('customer_name', ''),
                'customer_phone': stop_data.get('customer_phone', ''),
                'delivery_address': stop_data.get('delivery_address', ''),
                'delivery_notes': stop_data.get('delivery_notes', ''),
                'subtotal': stop_subtotal,
                'items': prepared_items,
            })

        order = DeliveryOrder.objects.create(
            shop=shop,
            day_session=day_session,
            driver=driver,
            subtotal=order_subtotal,
            delivery_cost=delivery_cost,
            total=order_subtotal + delivery_cost,
            status='pending',
            created_by=request.user,
        )

        for stop_data in prepared_stops:
            stop = DeliveryStop.objects.create(
                order=order,
                sequence=stop_data['sequence'],
                customer=stop_data['customer'],
                customer_name=stop_data['customer_name'],
                customer_phone=stop_data['customer_phone'],
                delivery_address=stop_data['delivery_address'],
                delivery_notes=stop_data['delivery_notes'],
                subtotal=stop_data['subtotal'],
            )
            for item in stop_data['items']:
                DeliveryStopItem.objects.create(
                    stop=stop,
                    product=item['product'],
                    variant=item['variant'],
                    quantity=item['quantity'],
                    unit_price=item['unit_price'],
                    buying_price=item['buying_price'],
                    line_total=item['line_total'],
                )

    return JsonResponse({
        'success': True,
        'order_number': order.order_number,
        'order_id': order.id,
    })


# ── Order Detail ─────────────────────────────────────────────────────────────

@login_required
def order_detail(request, pk):
    shop = get_current_shop(request)
    if not shop:
        return redirect('shop_select')

    order = get_object_or_404(DeliveryOrder, pk=pk, shop=shop)
    return render(request, 'delivery/order_detail.html', {
        'order': order,
        'shop': shop,
    })


# ── Mark Picked Up ────────────────────────────────────────────────────────────

@login_required
@require_POST
def mark_picked_up(request, pk):
    shop = get_current_shop(request)
    order = get_object_or_404(DeliveryOrder, pk=pk, shop=shop, status='pending')
    order.status = 'picked_up'
    order.picked_up_at = timezone.now()
    order.save(update_fields=['status', 'picked_up_at'])
    messages.success(request, f"Order {order.order_number} marked as picked up.")
    return redirect('delivery:board')


# ── Close Order ───────────────────────────────────────────────────────────────

@login_required
def close_order(request, pk):
    shop = get_current_shop(request)
    if not shop:
        return redirect('shop_select')

    order = get_object_or_404(DeliveryOrder, pk=pk, shop=shop)
    if not order.is_open:
        messages.warning(request, "This order is already closed.")
        return redirect('delivery:order_detail', pk=pk)

    if request.method == 'POST':
        return _process_close_order(request, shop, order)

    return render(request, 'delivery/close_order.html', {
        'order': order,
        'shop': shop,
    })


def _process_close_order(request, shop, order):
    payment_method = request.POST.get('payment_method', 'cash')
    amount_paid = Decimal(request.POST.get('amount_paid', '0') or '0')

    today = timezone.now().date()
    day_session = DaySession.objects.filter(shop=shop, date=today, status='open').first()
    if not day_session:
        messages.error(request, 'Day is not open. Please open the day first.')
        return redirect('delivery:close_order', pk=order.pk)

    from settings_app.models import ShopSettings
    shop_settings, _ = ShopSettings.objects.get_or_create(shop=shop, defaults={'tax_rate': 0})
    allow_negative_stock = shop_settings.allow_negative_stock

    # Collect all items across all stops
    all_stop_items = []
    for stop in order.stops.prefetch_related('items__product', 'items__variant'):
        for item in stop.items.all():
            all_stop_items.append(item)

    with transaction.atomic():
        # Validate stock across all stops
        for item in all_stop_items:
            if item.product.track_stock and not allow_negative_stock:
                sl = StockLevel.objects.select_for_update().filter(
                    product=item.product, variant=item.variant, shop=shop
                ).first()
                if not sl or sl.quantity < item.quantity:
                    avail = sl.quantity if sl else 0
                    messages.error(request, f'Insufficient stock for {item.product.name}. Available: {avail}')
                    return redirect('delivery:close_order', pk=order.pk)

        change = amount_paid - order.total if payment_method == 'cash' else Decimal('0')

        sale = Sale.objects.create(
            shop=shop,
            day_session=day_session,
            customer=None,
            cashier=request.user,
            subtotal=order.subtotal,
            tax_amount=Decimal('0'),
            discount_amount=Decimal('0'),
            total=order.total,
            payment_method=payment_method,
            amount_paid=amount_paid,
            change_given=max(change, Decimal('0')),
            status='completed',
            notes=f"Delivery {order.order_number} — Driver: {order.driver.name} — {order.stops_count} stop(s)",
        )

        for item in all_stop_items:
            SaleItem.objects.create(
                sale=sale,
                product=item.product,
                variant=item.variant,
                quantity=item.quantity,
                unit_price=item.unit_price,
                buying_price=item.buying_price,
                discount=Decimal('0'),
                line_total=item.line_total,
            )

            if item.product.track_stock:
                sl = StockLevel.objects.select_for_update().get(
                    product=item.product, variant=item.variant, shop=shop,
                )
                qty_before = sl.quantity
                sl.quantity -= item.quantity
                sl.save()

                sm = StockMovement.objects.create(
                    product=item.product,
                    variant=item.variant,
                    shop=shop,
                    movement_type='sale',
                    quantity=-item.quantity,
                    quantity_before=qty_before,
                    quantity_after=sl.quantity,
                    reference=sale.sale_number,
                    created_by=request.user,
                )
                from sync_engine.utils import queue_for_sync
                queue_for_sync(sm, 'create')
                queue_for_sync(sl, 'update')

        order.status = 'closed'
        order.sale = sale
        order.closed_by = request.user
        order.closed_at = timezone.now()
        order.save(update_fields=['status', 'sale', 'closed_by', 'closed_at'])

        from sync_engine.utils import queue_for_sync
        queue_for_sync(sale, 'create')

    messages.success(request, f"Order {order.order_number} closed. Sale {sale.sale_number} created.")
    return redirect('delivery:board')


# ── Cancel Order ──────────────────────────────────────────────────────────────

@login_required
@require_POST
def cancel_order(request, pk):
    shop = get_current_shop(request)
    order = get_object_or_404(DeliveryOrder, pk=pk, shop=shop)
    if not order.is_open:
        messages.warning(request, "Cannot cancel a closed order.")
        return redirect('delivery:order_detail', pk=pk)
    order.status = 'cancelled'
    order.save(update_fields=['status'])
    messages.success(request, f"Order {order.order_number} cancelled.")
    return redirect('delivery:board')


# ── Order History ─────────────────────────────────────────────────────────────

@login_required
def order_history(request):
    shop = get_current_shop(request)
    if not shop:
        return redirect('shop_select')

    orders = DeliveryOrder.objects.filter(shop=shop).select_related('driver', 'sale').prefetch_related('stops')

    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    driver_id = request.GET.get('driver', '')
    status = request.GET.get('status', '')

    if date_from:
        orders = orders.filter(created_at__date__gte=date_from)
    if date_to:
        orders = orders.filter(created_at__date__lte=date_to)
    if driver_id:
        orders = orders.filter(driver_id=driver_id)
    if status:
        orders = orders.filter(status=status)

    drivers = Driver.objects.filter(shop=shop)
    return render(request, 'delivery/history.html', {
        'orders': orders[:200],
        'drivers': drivers,
        'filters': {'date_from': date_from, 'date_to': date_to, 'driver': driver_id, 'status': status},
        'shop': shop,
    })


# ── Motorcycles ───────────────────────────────────────────────────────────────

@login_required
def motorcycles_list(request):
    shop = get_current_shop(request)
    if not shop:
        return redirect('shop_select')

    motorcycles = Motorcycle.objects.filter(shop=shop)
    return render(request, 'delivery/motorcycles.html', {
        'motorcycles': motorcycles,
        'shop': shop,
    })


@login_required
def motorcycle_form(request, pk=None):
    shop = get_current_shop(request)
    if not shop:
        return redirect('shop_select')

    motorcycle = get_object_or_404(Motorcycle, pk=pk, shop=shop) if pk else None

    if request.method == 'POST':
        plate = request.POST.get('plate_number', '').strip()
        if not plate:
            messages.error(request, 'Plate number is required.')
        else:
            if motorcycle:
                motorcycle.plate_number = plate
                motorcycle.make = request.POST.get('make', '').strip()
                motorcycle.model = request.POST.get('model', '').strip()
                motorcycle.color = request.POST.get('color', '').strip()
                motorcycle.status = request.POST.get('status', 'active')
                motorcycle.notes = request.POST.get('notes', '').strip()
                motorcycle.save()
                messages.success(request, f"Motorcycle {plate} updated.")
            else:
                Motorcycle.objects.create(
                    shop=shop,
                    plate_number=plate,
                    make=request.POST.get('make', '').strip(),
                    model=request.POST.get('model', '').strip(),
                    color=request.POST.get('color', '').strip(),
                    status=request.POST.get('status', 'active'),
                    notes=request.POST.get('notes', '').strip(),
                )
                messages.success(request, f"Motorcycle {plate} added.")
                if request.POST.get('action') == 'save_add':
                    return redirect('delivery:motorcycle_add')
            return redirect('delivery:motorcycles')

    return render(request, 'delivery/motorcycle_form.html', {
        'motorcycle': motorcycle,
        'shop': shop,
    })


# ── Drivers ───────────────────────────────────────────────────────────────────

@login_required
def drivers_list(request):
    shop = get_current_shop(request)
    if not shop:
        return redirect('shop_select')

    drivers = Driver.objects.filter(shop=shop).select_related('motorcycle')
    return render(request, 'delivery/drivers.html', {
        'drivers': drivers,
        'shop': shop,
    })


@login_required
def driver_form(request, pk=None):
    shop = get_current_shop(request)
    if not shop:
        return redirect('shop_select')

    driver = get_object_or_404(Driver, pk=pk, shop=shop) if pk else None
    motorcycles = Motorcycle.objects.filter(shop=shop, status='active')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'Driver name is required.')
        else:
            moto_id = request.POST.get('motorcycle') or None
            moto = Motorcycle.objects.filter(id=moto_id, shop=shop).first() if moto_id else None

            if driver:
                driver.name = name
                driver.phone = request.POST.get('phone', '').strip()
                driver.motorcycle = moto
                driver.is_active = request.POST.get('is_active') == 'on'
                driver.save()
                messages.success(request, f"Driver {name} updated.")
            else:
                Driver.objects.create(
                    shop=shop,
                    name=name,
                    phone=request.POST.get('phone', '').strip(),
                    motorcycle=moto,
                )
                messages.success(request, f"Driver {name} added.")
                if request.POST.get('action') == 'save_add':
                    return redirect('delivery:driver_add')
            return redirect('delivery:drivers')

    return render(request, 'delivery/driver_form.html', {
        'driver': driver,
        'motorcycles': motorcycles,
        'shop': shop,
    })
