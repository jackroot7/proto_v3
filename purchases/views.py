from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
from decimal import Decimal

from shops.models import Shop
from products.models import Product, ProductVariant
from stock.models import StockLevel, StockMovement
from .models import PurchaseOrder, PurchaseOrderItem, Supplier
from .forms import SupplierForm


def get_current_shop(request):
    shop_id = request.session.get('current_shop_id')
    return Shop.objects.filter(id=shop_id).first() if shop_id else None


# ── ORDER LIST ────────────────────────────────────────────────────
@login_required
def order_list(request):
    shop = get_current_shop(request)
    if not shop:
        return redirect('shop_select')
    from django.core.paginator import Paginator
    orders = PurchaseOrder.objects.filter(shop=shop).select_related(
        'supplier', 'created_by').prefetch_related('items')
    status_filter = request.GET.get('status', '')
    if status_filter:
        orders = orders.filter(status=status_filter)
    paginator = Paginator(orders, 20)
    page_obj  = paginator.get_page(request.GET.get('page'))
    return render(request, 'purchases/list.html', {
        'orders': page_obj, 'page_obj': page_obj,
        'shop': shop,
        'status_filter': status_filter,
        'status_choices': PurchaseOrder.STATUS_CHOICES,
    })


# ── ORDER CREATE — multi-product form ─────────────────────────────
@login_required
def order_create(request):
    shop = get_current_shop(request)
    if not shop:
        return redirect('shop_select')

    suppliers = Supplier.objects.filter(is_active=True)
    products  = Product.objects.filter(shop=shop, is_active=True).select_related('category')

    if request.method == 'POST':
        supplier_id   = request.POST.get('supplier')
        expected_date = request.POST.get('expected_date') or None
        notes         = request.POST.get('notes', '')

        if not supplier_id:
            messages.error(request, 'Please select a supplier.')
            return render(request, 'purchases/create.html', {
                'suppliers': suppliers, 'products': products, 'shop': shop})

        # Collect line items from the dynamic form rows
        product_ids = request.POST.getlist('product_id[]')
        variant_ids = request.POST.getlist('variant_id[]')
        quantities  = request.POST.getlist('quantity[]')
        unit_costs  = request.POST.getlist('unit_cost[]')

        if not any(q.strip() and int(q) > 0 for q in quantities if q.strip()):
            messages.error(request, 'Add at least one product to the order.')
            return render(request, 'purchases/create.html', {
                'suppliers': suppliers, 'products': products, 'shop': shop})

        with transaction.atomic():
            order = PurchaseOrder.objects.create(
                shop=shop,
                supplier_id=supplier_id,
                expected_date=expected_date or None,
                notes=notes,
                created_by=request.user,
                status='draft',
            )

            for pid, vid, qty, cost in zip(product_ids, variant_ids, quantities, unit_costs):
                pid  = pid.strip()
                qty  = qty.strip()
                cost = cost.strip()
                if not pid or not qty or not cost:
                    continue
                qty = int(qty)
                if qty <= 0:
                    continue
                variant = None
                if vid and vid.strip():
                    try:
                        variant = ProductVariant.objects.get(pk=int(vid.strip()))
                    except ProductVariant.DoesNotExist:
                        pass
                PurchaseOrderItem.objects.create(
                    order=order,
                    product_id=int(pid),
                    variant=variant,
                    quantity_ordered=qty,
                    unit_cost=Decimal(cost),
                )

            order.recalculate_totals()

        messages.success(request, f'Purchase order {order.order_number} created.')
        return redirect('purchases:detail', pk=order.pk)

    return render(request, 'purchases/create.html', {
        'suppliers': suppliers, 'products': products, 'shop': shop})


@login_required
def order_detail(request, pk):
    shop  = get_current_shop(request)
    order = get_object_or_404(PurchaseOrder, pk=pk, shop=shop)
    items = order.items.select_related('product', 'product__category', 'variant')

    # Build progress tracker steps for template — avoids split filter
    step_defs = [
        ('draft',      'Draft'),
        ('confirmed',  'Confirmed'),
        ('in_transit', 'In Transit'),
        ('arrived',    'Arrived'),
        ('received',   'Received'),
    ]
    status_order = ['draft', 'confirmed', 'in_transit', 'arrived', 'partial', 'received']
    current_idx = status_order.index(order.status) if order.status in status_order else 0
    steps_display = []
    for i, (slug, label) in enumerate(step_defs):
        step_idx = status_order.index(slug)
        if order.status == 'received':
            bg, color, num = '#0D512B', '#fff', '✓'
        elif step_idx < current_idx:
            bg, color, num = '#0D512B', '#fff', str(i + 1)
        elif step_idx == current_idx or (slug == 'arrived' and order.status == 'partial'):
            bg, color, num = '#6146c1', '#fff', str(i + 1)
        else:
            bg, color, num = '#f0f0f2', '#6b6b80', str(i + 1)
        steps_display.append({'label': label, 'bg': bg, 'color': color, 'num': num})

    return render(request, 'purchases/detail.html', {
        'order': order, 'items': items, 'shop': shop,
        'steps_display': steps_display,
        'total_received': sum(i.quantity_received for i in items),
    })


# ── ADD ITEM TO EXISTING DRAFT ORDER ─────────────────────────────
@login_required
@require_POST
def add_item(request, pk):
    shop  = get_current_shop(request)
    order = get_object_or_404(PurchaseOrder, pk=pk, shop=shop)
    if not order.is_editable:
        messages.error(request, 'Cannot edit a confirmed order.')
        return redirect('purchases:detail', pk=pk)

    product_id = request.POST.get('product_id')
    variant_id = request.POST.get('variant_id') or None
    qty        = int(request.POST.get('quantity', 0))
    cost       = Decimal(request.POST.get('unit_cost', '0'))

    if not product_id or qty <= 0:
        messages.error(request, 'Product and quantity are required.')
        return redirect('purchases:detail', pk=pk)

    variant = ProductVariant.objects.filter(pk=variant_id).first() if variant_id else None
    PurchaseOrderItem.objects.create(
        order=order, product_id=product_id, variant=variant,
        quantity_ordered=qty, unit_cost=cost)
    order.recalculate_totals()
    messages.success(request, 'Item added.')
    return redirect('purchases:detail', pk=pk)


# ── REMOVE ITEM FROM DRAFT ORDER ─────────────────────────────────
@login_required
@require_POST
def remove_item(request, pk, item_pk):
    shop  = get_current_shop(request)
    order = get_object_or_404(PurchaseOrder, pk=pk, shop=shop)
    if not order.is_editable:
        messages.error(request, 'Cannot edit a confirmed order.')
        return redirect('purchases:detail', pk=pk)
    order.items.filter(pk=item_pk).delete()
    order.recalculate_totals()
    messages.success(request, 'Item removed.')
    return redirect('purchases:detail', pk=pk)


# ── CONFIRM ORDER (send to supplier) ─────────────────────────────
@login_required
@require_POST
def confirm_order(request, pk):
    shop  = get_current_shop(request)
    order = get_object_or_404(PurchaseOrder, pk=pk, shop=shop)
    if not order.can_confirm:
        messages.error(request, 'Order cannot be confirmed in its current state.')
        return redirect('purchases:detail', pk=pk)
    order.status = 'confirmed'
    order.confirmed_by = request.user
    order.save(update_fields=['status', 'confirmed_by'])
    messages.success(request, f'{order.order_number} confirmed and sent to {order.supplier.name}.')
    return redirect('purchases:detail', pk=pk)


# ── MARK AS IN TRANSIT ────────────────────────────────────────────
@login_required
@require_POST
def mark_in_transit(request, pk):
    shop  = get_current_shop(request)
    order = get_object_or_404(PurchaseOrder, pk=pk, shop=shop)
    order.status = 'in_transit'
    order.save(update_fields=['status'])
    messages.success(request, f'{order.order_number} marked as in transit.')
    return redirect('purchases:detail', pk=pk)


# ── MARK AS ARRIVED (triggers inspection) ────────────────────────
@login_required
@require_POST
def mark_arrived(request, pk):
    shop  = get_current_shop(request)
    order = get_object_or_404(PurchaseOrder, pk=pk, shop=shop)
    if not order.can_mark_arrived:
        messages.error(request, 'Order must be confirmed or in transit to mark as arrived.')
        return redirect('purchases:detail', pk=pk)
    order.status      = 'arrived'
    order.arrived_date = timezone.now().date()
    order.save(update_fields=['status', 'arrived_date'])
    messages.success(request, f'{order.order_number} marked as arrived. Ready for inspection.')
    return redirect('purchases:inspect', pk=pk)


# ── INSPECTION PAGE ───────────────────────────────────────────────
@login_required
def inspect_order(request, pk):
    """
    Inspection page: for each item, enter how many are accepted (good)
    and how many are rejected (damaged/wrong). Auto-stocks accepted quantities.
    """
    shop  = get_current_shop(request)
    order = get_object_or_404(PurchaseOrder, pk=pk, shop=shop)
    if order.status not in ('arrived', 'partial'):
        messages.error(request, 'Order is not ready for inspection.')
        return redirect('purchases:detail', pk=pk)

    items = order.items.select_related('product', 'variant')

    if request.method == 'POST':
        with transaction.atomic():
            all_done = True
            for item in items:
                accepted_key = f'accepted_{item.pk}'
                rejected_key = f'rejected_{item.pk}'
                notes_key    = f'notes_{item.pk}'

                accepted = int(request.POST.get(accepted_key, 0) or 0)
                rejected = int(request.POST.get(rejected_key, 0) or 0)
                notes    = request.POST.get(notes_key, '').strip()

                # Validate: accepted + rejected <= remaining pending
                max_allowed = item.quantity_ordered - item.quantity_received - item.quantity_rejected
                accepted = min(accepted, max_allowed)
                rejected = min(rejected, max_allowed - accepted)

                if accepted > 0:
                    # Auto-stock: update StockLevel
                    sl, _ = StockLevel.objects.get_or_create(
                        product=item.product,
                        variant=item.variant,
                        shop=shop,
                        defaults={'quantity': 0}
                    )
                    qty_before    = sl.quantity
                    sl.quantity  += accepted
                    sl.save()

                    # Update buying price to latest cost
                    item.product.buying_price = item.unit_cost
                    item.product.save(update_fields=['buying_price'])

                    sm = StockMovement.objects.create(
                        product       = item.product,
                        variant       = item.variant,
                        shop          = shop,
                        movement_type = 'purchase',
                        quantity      = accepted,
                        quantity_before = qty_before,
                        quantity_after  = sl.quantity,
                        reference     = order.order_number,
                        notes         = f'Inspection: {accepted} accepted, {rejected} rejected. {notes}',
                        created_by    = request.user,
                    )
                    from sync_engine.utils import queue_for_sync
                    queue_for_sync(sm, 'create')

                item.quantity_received += accepted
                item.quantity_rejected += rejected
                item.inspection_notes  = notes
                item.save(update_fields=['quantity_received', 'quantity_rejected', 'inspection_notes'])

                # Item is "done" when accepted + rejected accounts for all ordered units
                if (item.quantity_received + item.quantity_rejected) < item.quantity_ordered:
                    all_done = False

            # Update order status
            order.received_by = request.user
            total_received = sum(i.quantity_received for i in order.items.all())
            if all_done:
                order.status        = 'received'
                order.received_date = timezone.now().date()
            else:
                order.status = 'partial'
            order.save(update_fields=['status', 'received_date', 'received_by'])

        total_accepted = sum(i.quantity_received for i in order.items.all())
        total_rejected = sum(i.quantity_rejected for i in order.items.all())
        if all_done:
            msg = f'Inspection complete. {total_accepted} unit(s) accepted and added to stock.'
            if total_rejected:
                msg += f' {total_rejected} unit(s) rejected — not added to stock.'
        else:
            msg = 'Partial receipt saved. Re-open inspection when remaining items arrive.'
        messages.success(request, msg)
        return redirect('purchases:detail', pk=pk)

    return render(request, 'purchases/inspect.html', {
        'order': order, 'items': items, 'shop': shop})


# ── CANCEL ORDER ──────────────────────────────────────────────────
@login_required
@require_POST
def cancel_order(request, pk):
    shop  = get_current_shop(request)
    order = get_object_or_404(PurchaseOrder, pk=pk, shop=shop)

    if order.status == 'cancelled':
        messages.info(request, 'Order is already cancelled.')
        return redirect('purchases:detail', pk=pk)

    # Check if any stock was already received (partial or full receipt)
    items_with_stock = [i for i in order.items.all() if i.quantity_received > 0]

    if items_with_stock:
        # Confirm required — stock will be reversed
        confirmed = request.POST.get('confirm_stock_reversal') == 'yes'
        if not confirmed:
            messages.error(
                request,
                f'{order.order_number} has {sum(i.quantity_received for i in items_with_stock)} '
                f'unit(s) already received and stocked. '
                f'Submit with confirm_stock_reversal=yes to reverse stock and cancel.'
            )
            return redirect('purchases:detail', pk=pk)

        # Reverse stock for every item that was received
        with transaction.atomic():
            for item in items_with_stock:
                if item.quantity_received <= 0:
                    continue
                sl = StockLevel.objects.filter(
                    product=item.product,
                    variant=item.variant,
                    shop=shop,
                ).first()
                if sl:
                    qty_before = sl.quantity
                    sl.quantity = max(0, sl.quantity - item.quantity_received)
                    sl.save()
                    StockMovement.objects.create(
                        product=item.product,
                        variant=item.variant,
                        shop=shop,
                        movement_type='adjustment',
                        quantity=-item.quantity_received,
                        quantity_before=qty_before,
                        quantity_after=sl.quantity,
                        reference=f'CANCEL-{order.order_number}',
                        notes=f'Stock reversed: purchase order {order.order_number} cancelled.',
                        created_by=request.user,
                    )
            order.status = 'cancelled'
            order.save(update_fields=['status'])

        reversed_units = sum(i.quantity_received for i in items_with_stock)
        messages.success(
            request,
            f'{order.order_number} cancelled. '
            f'{reversed_units} unit(s) removed from stock.'
        )
    else:
        # No stock was received — safe to cancel directly
        order.status = 'cancelled'
        order.save(update_fields=['status'])
        messages.success(request, f'{order.order_number} cancelled.')

    return redirect('purchases:list')


# ── SUPPLIER VIEWS ────────────────────────────────────────────────
@login_required
def supplier_list(request):
    suppliers = Supplier.objects.filter(is_active=True).prefetch_related('orders')
    return render(request, 'purchases/suppliers.html', {'suppliers': suppliers})


@login_required
def supplier_create(request):
    if request.method == 'POST':
        form = SupplierForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Supplier added.')
            return redirect('purchases:suppliers')
    else:
        form = SupplierForm()
    return render(request, 'purchases/supplier_form.html', {'form': form})


@login_required
def supplier_edit(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == 'POST':
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            form.save()
            messages.success(request, 'Supplier updated.')
            return redirect('purchases:suppliers')
    else:
        form = SupplierForm(instance=supplier)
    return render(request, 'purchases/supplier_form.html', {
        'form': form, 'supplier': supplier})


# ── AJAX: get variants for a product (used in order create form) ──
@login_required
def product_variants_json(request, product_pk):
    shop = get_current_shop(request)
    product = get_object_or_404(Product, pk=product_pk, shop=shop)
    variants = []
    for v in product.variants.filter(is_active=True):
        label = ', '.join(f"{a.variant_type.name}: {a.value}" for a in v.attributes.all())
        variants.append({'id': v.pk, 'label': label,
                         'buying_price': str(v.effective_buying_price)})
    return JsonResponse({'variants': variants, 'has_variants': product.has_variants,
                         'buying_price': str(product.buying_price)})