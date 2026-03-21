from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from shops.models import Shop
from products.models import Product
from .models import StockLevel, StockMovement, StockTake, StockTakeItem


def get_current_shop(request):
    shop_id = request.session.get('current_shop_id')
    return Shop.objects.filter(id=shop_id).first() if shop_id else None


@login_required
def stock_list(request):
    shop = get_current_shop(request)
    if not shop:
        return redirect('shop_select')
    from django.conf import settings
    threshold = getattr(settings, 'PROTO_LOW_STOCK_THRESHOLD', 10)
    levels = StockLevel.objects.filter(shop=shop).select_related(
        'product', 'product__category', 'variant'
    ).order_by('quantity')

    search = request.GET.get('q', '')
    status = request.GET.get('status', '')
    if search:
        levels = levels.filter(product__name__icontains=search)
    if status == 'low':
        levels = [l for l in levels if l.is_low]
    elif status == 'critical':
        levels = [l for l in levels if l.is_critical]

    total_value = sum(l.quantity * l.product.buying_price for l in StockLevel.objects.filter(shop=shop))

    from django.core.paginator import Paginator
    paginator = Paginator(levels if isinstance(levels, list) else levels, 30)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'stock/list.html', {
        'levels': page_obj, 'page_obj': page_obj,
        'shop': shop,
        'total_value': total_value,
        'search': search,
        'status_filter': status,
    })


@login_required
def adjust_stock(request, product_pk):
    shop = get_current_shop(request)
    product = get_object_or_404(Product, pk=product_pk, shop=shop)
    sl, _ = StockLevel.objects.get_or_create(
        product=product, variant=None, shop=shop, defaults={'quantity': 0}
    )

    # Types that ADD to stock
    ADD_TYPES = {'opening', 'return', 'transfer_in', 'found'}
    # Types that REDUCE stock
    REDUCE_TYPES = {'write_off', 'damage', 'theft', 'expired', 'transfer_out'}

    if request.method == 'POST':
        direction     = request.POST.get('direction', 'add')   # 'add' or 'reduce'
        qty_raw       = request.POST.get('quantity', '0').strip()
        movement_type = request.POST.get('movement_type', 'adjustment')
        notes         = request.POST.get('notes', '').strip()

        # Validate quantity
        try:
            qty = int(qty_raw)
        except ValueError:
            messages.error(request, 'Please enter a valid whole number.')
            return render(request, 'stock/adjust.html', {
                'product': product, 'shop': shop, 'stock_level': sl})

        if qty <= 0:
            messages.error(request, 'Quantity must be greater than zero.')
            return render(request, 'stock/adjust.html', {
                'product': product, 'shop': shop, 'stock_level': sl})

        # Determine signed delta based on direction
        if direction == 'reduce' or movement_type in REDUCE_TYPES:
            delta = -qty
        else:
            delta = qty

        # Prevent stock going negative
        new_qty = sl.quantity + delta
        if new_qty < 0:
            messages.error(
                request,
                f'Cannot reduce by {qty} — only {sl.quantity} unit(s) in stock. '
                f'Maximum you can reduce is {sl.quantity}.'
            )
            return render(request, 'stock/adjust.html', {
                'product': product, 'shop': shop, 'stock_level': sl})

        qty_before  = sl.quantity
        sl.quantity = new_qty
        sl.save()

        movement = StockMovement.objects.create(
            product=product,
            shop=shop,
            movement_type='adjustment',
            quantity=delta,
            quantity_before=qty_before,
            quantity_after=sl.quantity,
            notes=f'[{movement_type.replace("_", " ").title()}] {notes}',
            created_by=request.user,
        )

        direction_word = 'added to' if delta > 0 else 'removed from'
        from sync_engine.utils import queue_for_sync
        queue_for_sync(movement, 'create')
        messages.success(
            request,
            f'{qty} unit(s) {direction_word} {product.name}. '
            f'New stock: {sl.quantity}.'
        )
        return redirect('stock:list')

    return render(request, 'stock/adjust.html', {
        'product': product,
        'shop': shop,
        'stock_level': sl,
    })


@login_required
def movement_history(request):
    shop = get_current_shop(request)
    from django.core.paginator import Paginator
    movements_qs = StockMovement.objects.filter(shop=shop).select_related(
        'product', 'product__uom', 'created_by'
    ).order_by('-created_at')
    paginator = Paginator(movements_qs, 30)
    page_obj  = paginator.get_page(request.GET.get('page'))
    return render(request, 'stock/movements.html', {
        'movements': page_obj, 'page_obj': page_obj, 'shop': shop
    })


@login_required
def stock_take_create(request):
    shop = get_current_shop(request)
    if request.method == 'POST':
        take = StockTake.objects.create(
            shop=shop, date=timezone.now().date(), conducted_by=request.user, status='in_progress'
        )
        products = Product.objects.filter(shop=shop, is_active=True, track_stock=True)
        for p in products:
            sl = StockLevel.objects.filter(product=p, shop=shop).first()
            StockTakeItem.objects.create(
                stock_take=take, product=p, system_quantity=sl.quantity if sl else 0
            )
        messages.success(request, 'Stock take started.')
        return redirect('stock:take_detail', pk=take.pk)
    return render(request, 'stock/take_start.html', {'shop': shop})


@login_required
def stock_take_detail(request, pk):
    shop = get_current_shop(request)
    take = get_object_or_404(StockTake, pk=pk, shop=shop)
    if request.method == 'POST':
        for item in take.items.all():
            counted = request.POST.get(f'item_{item.pk}')
            if counted is not None:
                item.counted_quantity = int(counted)
                item.save()
        if 'complete' in request.POST:
            take.status = 'completed'
            take.completed_at = timezone.now()
            take.save()
            # Apply adjustments
            for item in take.items.filter(counted_quantity__isnull=False):
                if item.discrepancy != 0:
                    sl, _ = StockLevel.objects.get_or_create(
                        product=item.product, variant=None, shop=shop, defaults={'quantity': 0}
                    )
                    sl.quantity = item.counted_quantity
                    sl.save()
                    StockMovement.objects.create(
                        product=item.product, shop=shop, movement_type='adjustment',
                        quantity=item.discrepancy,
                        quantity_before=item.system_quantity,
                        quantity_after=item.counted_quantity,
                        reference=f'TAKE-{take.pk}',
                        created_by=request.user,
                    )
            messages.success(request, 'Stock take completed and adjustments applied.')
            return redirect('stock:list')
        messages.success(request, 'Counts saved.')
        return redirect('stock:take_detail', pk=pk)
    return render(request, 'stock/take_detail.html', {'take': take, 'shop': shop})