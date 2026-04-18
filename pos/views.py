from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
import json

from shops.models import Shop, DaySession
from products.models import Product, ProductVariant, Category, ProductPriceTier
from customers.models import Customer
from stock.models import StockLevel, StockMovement
from .models import Sale, SaleItem, Return, ReturnItem


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

    # Build tier lookup dicts for JS: {product_id: [{min_qty, price},...]}
    import json as _json
    all_tiers = ProductPriceTier.objects.filter(
        product__shop=shop
    ).order_by('-min_quantity')
    product_tiers: dict = {}
    variant_tiers: dict = {}
    for t in all_tiers:
        entry = {'min_qty': t.min_quantity, 'price': float(t.unit_price)}
        if t.variant_id:
            variant_tiers.setdefault(t.variant_id, []).append(entry)
        else:
            product_tiers.setdefault(t.product_id, []).append(entry)

    return render(request, 'pos/index.html', {
        'shop': shop,
        'day_session': day_session,
        'categories': categories,
        'product_data': product_data,
        'customers': customers,
        'selected_category': cat_filter,
        'search': search,
        'shop_settings': shop_settings,
        'product_tiers_json': _json.dumps(product_tiers),
        'variant_tiers_json': _json.dumps(variant_tiers),
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

    sale_discount = Decimal(str(data.get('sale_discount', 0) or 0))

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
            base_price   = variant.effective_selling_price if variant else (product.selling_price or Decimal('0'))
            buying_price = variant.effective_buying_price  if variant else (product.buying_price  or Decimal('0'))

            # Apply bulk/tiered price server-side
            tiers = ProductPriceTier.objects.filter(
                product=product,
                variant=variant,
                min_quantity__lte=qty,
            ).order_by('-min_quantity').first()
            if tiers is None and variant:
                # Fall back to product-level tier (no variant filter)
                tiers = ProductPriceTier.objects.filter(
                    product=product,
                    variant__isnull=True,
                    min_quantity__lte=qty,
                ).order_by('-min_quantity').first()
            unit_price = tiers.unit_price if tiers else base_price

            # Per-item discount (amount, not percentage) — JS sends as 'item_discount'
            item_discount = Decimal(str(item_data.get('item_discount', item_data.get('discount', 0)) or 0))

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

            line_total = max(Decimal('0'), unit_price * qty - item_discount)
            subtotal += line_total
            sale_items.append({
                'product': product,
                'variant': variant,
                'quantity': qty,
                'unit_price': unit_price,
                'buying_price': buying_price,
                'discount': item_discount,
                'line_total': line_total,
            })

        tax_amount = subtotal * TAX_RATE
        total = max(Decimal('0'), subtotal + tax_amount - sale_discount)
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
            discount_amount=sale_discount,
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
                discount=item['discount'],
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

                sm = StockMovement.objects.create(
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
                from sync_engine.utils import queue_for_sync
                queue_for_sync(sm, 'create')
                queue_for_sync(sl, 'update')

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
        'sale_discount': float(sale.discount_amount),
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
        'sales': page_obj,
        'page_obj': page_obj,
        'shop': shop,
        'filter_date': filter_date,
        'today': today,
        'current_role': request.session.get('current_role', 'cashier'),
    })


@login_required
@require_POST
def void_sale(request, sale_id):
    shop = get_current_shop(request)
    role = request.session.get('current_role', 'cashier')
    if role == 'cashier':
        return JsonResponse({'success': False, 'error': 'Permission denied. Only admins can void sales.'}, status=403)

    sale = get_object_or_404(Sale, id=sale_id, shop=shop, status__in=['completed', 'partially_returned'])

    if not sale.day_session or not sale.day_session.is_open:
        return JsonResponse({'success': False, 'error': 'Cannot void a sale from a closed day session.'}, status=400)

    with transaction.atomic():
        sale.status = 'voided'
        sale.voided_by = request.user
        sale.void_reason = request.POST.get('reason', '')
        sale.save()

        # Restore only the net qty still outstanding (already-returned items are already back in stock)
        for item in sale.items.prefetch_related('returns').all():
            already_returned = sum(ri.quantity for ri in item.returns.all())
            net_qty = item.quantity - already_returned
            if not item.product.track_stock or net_qty <= 0:
                continue
            sl, _ = StockLevel.objects.get_or_create(
                product=item.product, variant=item.variant, shop=shop,
                defaults={'quantity': 0},
            )
            qty_before = sl.quantity
            sl.quantity += net_qty
            sl.save()
            vm = StockMovement.objects.create(
                product=item.product, variant=item.variant, shop=shop,
                movement_type='return',
                quantity=net_qty,
                quantity_before=qty_before,
                quantity_after=sl.quantity,
                reference=f"VOID-{sale.sale_number}",
                created_by=request.user,
            )
            from sync_engine.utils import queue_for_sync
            queue_for_sync(vm, 'create')
            queue_for_sync(sl, 'update')

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


# ── Returns ──────────────────────────────────────────────────────────────────

@login_required
def create_return(request, sale_id):
    from django.contrib import messages
    shop = get_current_shop(request)
    if not shop:
        return redirect('shop_select')

    sale = get_object_or_404(Sale, id=sale_id, shop=shop)

    if sale.status == 'voided':
        messages.error(request, 'Cannot return items from a voided sale.')
        return redirect('pos:history')

    if not sale.day_session or not sale.day_session.is_open:
        messages.error(request, 'Cannot process returns for sales from a closed day session.')
        return redirect('pos:history')

    # Build returnable items list
    items_data = []
    for item in sale.items.select_related('product', 'variant').all():
        already_returned = sum(ri.quantity for ri in item.returns.all())
        returnable = item.quantity - already_returned
        if returnable > 0:
            items_data.append({
                'sale_item': item,
                'already_returned': already_returned,
                'returnable': returnable,
            })

    if not items_data:
        messages.error(request, 'All items in this sale have already been returned.')
        return redirect('pos:history')

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        refund_method = request.POST.get('refund_method', 'cash')

        return_items_to_create = []
        total_refund = Decimal('0')
        errors = []

        for item_data in items_data:
            item = item_data['sale_item']
            try:
                qty = int(request.POST.get(f'qty_{item.id}', '0'))
            except (ValueError, TypeError):
                qty = 0

            if qty <= 0:
                continue
            if qty > item_data['returnable']:
                errors.append(f'Cannot return more than {item_data["returnable"]} of {item.product.name}.')
                continue

            line_refund = item.unit_price * qty
            total_refund += line_refund
            return_items_to_create.append({
                'sale_item': item,
                'product': item.product,
                'variant': item.variant,
                'quantity': qty,
                'unit_price': item.unit_price,
                'line_total': line_refund,
            })

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, 'pos/return_form.html', {
                'sale': sale, 'items_data': items_data, 'shop': shop,
            })

        if not return_items_to_create:
            messages.error(request, 'Please enter a quantity for at least one item to return.')
            return render(request, 'pos/return_form.html', {
                'sale': sale, 'items_data': items_data, 'shop': shop,
            })

        with transaction.atomic():
            ret = Return.objects.create(
                sale=sale,
                shop=shop,
                day_session=sale.day_session,
                processed_by=request.user,
                reason=reason,
                refund_method=refund_method,
                total_refund=total_refund,
            )

            for ri_data in return_items_to_create:
                ReturnItem.objects.create(
                    return_obj=ret,
                    sale_item=ri_data['sale_item'],
                    product=ri_data['product'],
                    variant=ri_data['variant'],
                    quantity=ri_data['quantity'],
                    unit_price=ri_data['unit_price'],
                    line_total=ri_data['line_total'],
                )

                if ri_data['product'].track_stock:
                    sl, _ = StockLevel.objects.get_or_create(
                        product=ri_data['product'],
                        variant=ri_data['variant'],
                        shop=shop,
                        defaults={'quantity': 0},
                    )
                    qty_before = sl.quantity
                    sl.quantity += ri_data['quantity']
                    sl.save()

                    sm = StockMovement.objects.create(
                        product=ri_data['product'],
                        variant=ri_data['variant'],
                        shop=shop,
                        movement_type='return',
                        quantity=ri_data['quantity'],
                        quantity_before=qty_before,
                        quantity_after=sl.quantity,
                        reference=f"RET-{sale.sale_number}",
                        created_by=request.user,
                    )
                    from sync_engine.utils import queue_for_sync
                    queue_for_sync(sm, 'create')
                    queue_for_sync(sl, 'update')

            # Refresh items to get updated return counts
            total_sold = sum(i.quantity for i in sale.items.all())
            total_returned = sum(
                sum(ri.quantity for ri in i.returns.all())
                for i in sale.items.all()
            )
            if total_returned >= total_sold:
                sale.status = 'refunded'
            else:
                sale.status = 'partially_returned'
            sale.synced = False
            sale.save(update_fields=['status', 'synced'])

            from sync_engine.utils import queue_for_sync
            queue_for_sync(ret, 'create')
            queue_for_sync(sale, 'update')

        messages.success(request, f'Return {ret.return_number} processed successfully.')
        return redirect('pos:return_detail', return_id=ret.id)

    return render(request, 'pos/return_form.html', {
        'sale': sale,
        'items_data': items_data,
        'shop': shop,
    })


@login_required
def return_detail(request, return_id):
    shop = get_current_shop(request)
    ret = get_object_or_404(Return, id=return_id, shop=shop)
    return render(request, 'pos/return_detail.html', {'ret': ret, 'shop': shop})


@login_required
def return_history(request):
    shop = get_current_shop(request)
    if not shop:
        return redirect('shop_select')

    from django.core.paginator import Paginator
    import datetime

    today = timezone.now().date()
    date_filter = request.GET.get('date', str(today))
    try:
        filter_date = datetime.date.fromisoformat(date_filter)
    except Exception:
        filter_date = today

    returns_qs = Return.objects.filter(
        shop=shop, created_at__date=filter_date
    ).select_related('sale', 'processed_by').prefetch_related('items').order_by('-created_at')

    paginator = Paginator(returns_qs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'pos/return_history.html', {
        'returns': page_obj,
        'page_obj': page_obj,
        'shop': shop,
        'filter_date': filter_date,
        'today': today,
    })


# ── Sale Editing ──────────────────────────────────────────────────────────────

@login_required
def edit_sale(request, sale_id):
    from django.contrib import messages
    from settings_app.models import ShopSettings

    shop = get_current_shop(request)
    if not shop:
        return redirect('shop_select')

    role = request.session.get('current_role', 'cashier')
    if role == 'cashier':
        messages.error(request, 'Permission denied. Only admins can edit sales.')
        return redirect('pos:history')

    sale = get_object_or_404(Sale, id=sale_id, shop=shop)

    if sale.status not in ('completed', 'partially_returned'):
        messages.error(request, 'Only active sales can be edited.')
        return redirect('pos:history')

    if not sale.day_session or not sale.day_session.is_open:
        messages.error(request, 'Cannot edit sales from a closed day session.')
        return redirect('pos:history')

    # Build items with their return state
    items_data = []
    for item in sale.items.select_related('product', 'variant').prefetch_related('returns').all():
        qty_returned = sum(ri.quantity for ri in item.returns.all())
        items_data.append({
            'item': item,
            'qty_returned': qty_returned,
            'qty_min': qty_returned,
            'qty_remaining': item.quantity - qty_returned,
            'fully_returned': qty_returned >= item.quantity,
        })

    if request.method == 'POST':
        shop_settings, _ = ShopSettings.objects.get_or_create(
            shop=shop, defaults={'tax_rate': 18.00}
        )
        allow_negative = shop_settings.allow_negative_stock
        TAX_RATE = Decimal(str(shop_settings.tax_rate / 100)) if shop_settings.tax_rate else Decimal('0.18')

        updates = {}
        for row in items_data:
            item = row['item']
            try:
                qty = int(request.POST.get(f'qty_{item.id}', item.quantity))
            except (ValueError, TypeError):
                qty = item.quantity
            # Clamp to valid range: [qty_returned, original]
            qty = max(row['qty_min'], qty)
            updates[item.id] = qty

        # At least one item must remain (with qty > qty_returned means it's still being sold)
        all_at_minimum = all(updates[r['item'].id] == r['qty_min'] for r in items_data)
        if all_at_minimum:
            messages.error(request, 'No active items remain after editing. Use Void to cancel the entire sale.')
            return render(request, 'pos/edit_sale.html', {
                'sale': sale, 'items_data': items_data, 'shop': shop,
            })

        # Pre-validate stock increases before touching anything
        for row in items_data:
            item = row['item']
            new_qty = updates[item.id]
            delta = item.quantity - new_qty  # positive = restore stock, negative = need more
            if delta < 0 and item.product.track_stock and not allow_negative:
                need = abs(delta)
                sl = StockLevel.objects.filter(
                    product=item.product, variant=item.variant, shop=shop
                ).first()
                available = sl.quantity if sl else 0
                if available < need:
                    messages.error(
                        request,
                        f'Insufficient stock for {item.product.name}. '
                        f'Need {need} more, only {available} available.'
                    )
                    return render(request, 'pos/edit_sale.html', {
                        'sale': sale, 'items_data': items_data, 'shop': shop,
                    })

        with transaction.atomic():
            new_subtotal = Decimal('0')

            for row in items_data:
                item = row['item']
                qty_returned = row['qty_min']
                new_qty = updates[item.id]
                # delta = full original qty vs new qty; this correctly captures the NET stock change
                # because: stock already had +qty_returned restored; we only move the remainder
                delta = item.quantity - new_qty

                if new_qty == qty_returned:
                    # All remaining (unreturned) units have been edited out — remove the line
                    net_restore = item.quantity - qty_returned  # only restore outstanding stock
                    if item.product.track_stock and net_restore > 0:
                        sl, _ = StockLevel.objects.get_or_create(
                            product=item.product, variant=item.variant, shop=shop,
                            defaults={'quantity': 0},
                        )
                        qty_before = sl.quantity
                        sl.quantity += net_restore
                        sl.save()
                        sm = StockMovement.objects.create(
                            product=item.product, variant=item.variant, shop=shop,
                            movement_type='return',
                            quantity=net_restore,
                            quantity_before=qty_before,
                            quantity_after=sl.quantity,
                            reference=f"EDIT-{sale.sale_number}",
                            created_by=request.user,
                        )
                        from sync_engine.utils import queue_for_sync
                        queue_for_sync(sm, 'create')
                        queue_for_sync(sl, 'update')
                    item.delete()
                else:
                    if item.product.track_stock and delta != 0:
                        sl, _ = StockLevel.objects.get_or_create(
                            product=item.product, variant=item.variant, shop=shop,
                            defaults={'quantity': 0},
                        )
                        qty_before = sl.quantity
                        sl.quantity += delta
                        sl.save()
                        sm = StockMovement.objects.create(
                            product=item.product, variant=item.variant, shop=shop,
                            movement_type='return' if delta > 0 else 'sale',
                            quantity=delta,
                            quantity_before=qty_before,
                            quantity_after=sl.quantity,
                            reference=f"EDIT-{sale.sale_number}",
                            created_by=request.user,
                        )
                        from sync_engine.utils import queue_for_sync
                        queue_for_sync(sm, 'create')
                        queue_for_sync(sl, 'update')

                    item.quantity = new_qty
                    item.line_total = (item.unit_price * new_qty) - item.discount
                    item.save()
                    new_subtotal += item.line_total

            tax_amount = new_subtotal * TAX_RATE
            sale.subtotal = new_subtotal
            sale.tax_amount = tax_amount
            sale.total = new_subtotal + tax_amount
            sale.notes = (sale.notes + f'\n[Edited by {request.user.get_full_name() or request.user.username}]').strip()
            sale.synced = False
            sale.save(update_fields=['subtotal', 'tax_amount', 'total', 'notes', 'synced'])

            from sync_engine.utils import queue_for_sync
            queue_for_sync(sale, 'update')

        messages.success(request, f'Sale {sale.sale_number} updated successfully.')
        return redirect('pos:history')

    return render(request, 'pos/edit_sale.html', {
        'sale': sale,
        'items_data': items_data,
        'shop': shop,
    })