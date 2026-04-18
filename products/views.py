from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils.text import slugify
from django.db import transaction
from shops.models import Shop
from .models import (Product, Category, ProductVariant,
                     VariantType, VariantAttribute, ProductVariantType, ProductPriceTier)
from .forms import ProductForm, CategoryForm


def get_current_shop(request):
    shop_id = request.session.get('current_shop_id')
    return Shop.objects.filter(id=shop_id).first() if shop_id else None


@login_required
def product_list(request):
    shop = get_current_shop(request)
    if not shop:
        return redirect('shop_select')
    categories = Category.objects.filter(shop=shop, is_active=True)
    from django.core.paginator import Paginator
    products_qs = Product.objects.filter(shop=shop).select_related('category').prefetch_related(
        'variants__attributes__variant_type', 'stock_levels'
    ).order_by('category__name', 'name')
    cat_filter = request.GET.get('category', '')
    search = request.GET.get('q', '')
    if cat_filter:
        products_qs = products_qs.filter(category__slug=cat_filter)
    if search:
        products_qs = products_qs.filter(name__icontains=search)
    paginator = Paginator(products_qs, 25)
    page_obj  = paginator.get_page(request.GET.get('page'))
    return render(request, 'products/list.html', {
        'products': page_obj, 'page_obj': page_obj, 'categories': categories,
        'selected_category': cat_filter, 'search': search, 'shop': shop,
    })


@login_required
def product_detail(request, pk):
    shop = get_current_shop(request)
    product = get_object_or_404(Product, pk=pk, shop=shop)
    variant_types = ProductVariantType.objects.filter(
        product=product).select_related('variant_type')
    variants = ProductVariant.objects.filter(
        product=product).prefetch_related('attributes__variant_type')
    from stock.models import StockLevel, StockMovement
    stock = StockLevel.objects.filter(product=product, shop=shop).select_related('variant')
    movements = StockMovement.objects.filter(
        product=product, shop=shop).select_related('created_by').order_by('-created_at')[:20]
    # All distinct variant type names for this product
    vtype_names = list(variant_types.values_list('variant_type__name', flat=True))
    price_tiers = ProductPriceTier.objects.filter(product=product).select_related('variant').order_by('variant', 'min_quantity')
    return render(request, 'products/detail.html', {
        'product': product, 'variant_types': variant_types, 'variants': variants,
        'stock': stock, 'movements': movements, 'shop': shop,
        'vtype_names': vtype_names, 'price_tiers': price_tiers,
    })


@login_required
def product_create(request):
    shop = get_current_shop(request)
    if not shop:
        return redirect('shop_select')
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, shop=shop)
        if form.is_valid():
            product = form.save(commit=False)
            product.shop = shop
            product.save()
            messages.success(request, f'Product "{product.name}" created.')
            return redirect('products:detail', pk=product.pk)
    else:
        form = ProductForm(shop=shop)
    return render(request, 'products/form.html', {
        'form': form, 'shop': shop, 'action': 'Create'})


@login_required
def product_edit(request, pk):
    shop = get_current_shop(request)
    product = get_object_or_404(Product, pk=pk, shop=shop)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product, shop=shop)
        if form.is_valid():
            form.save()
            messages.success(request, f'Product "{product.name}" updated.')
            return redirect('products:detail', pk=product.pk)
    else:
        form = ProductForm(instance=product, shop=shop)
    return render(request, 'products/form.html', {
        'form': form, 'shop': shop, 'action': 'Edit', 'product': product})


@login_required
def category_list(request):
    shop = get_current_shop(request)
    categories = Category.objects.filter(shop=shop).prefetch_related('products')
    return render(request, 'products/categories.html', {
        'categories': categories, 'shop': shop})


@login_required
def category_create(request):
    shop = get_current_shop(request)
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            cat = form.save(commit=False)
            cat.shop = shop
            cat.slug = slugify(cat.name)
            base_slug = cat.slug
            n = 1
            while Category.objects.filter(slug=cat.slug).exists():
                cat.slug = f"{base_slug}-{n}"
                n += 1
            cat.save()
            messages.success(request, f'Category "{cat.name}" created.')
            return redirect('products:categories')
    else:
        form = CategoryForm()
    return render(request, 'products/category_form.html', {
        'form': form, 'shop': shop})


# ── VARIANT MANAGEMENT ──────────────────────────────────────────────────

@login_required
def variant_manager(request, product_pk):
    """
    Full variant management page for a product.
    Handles adding variant types, adding option values,
    and generating variant combinations.
    """
    shop = get_current_shop(request)
    product = get_object_or_404(Product, pk=product_pk, shop=shop)
    variant_types = ProductVariantType.objects.filter(
        product=product).select_related('variant_type').prefetch_related(
        'variant_type__variantattribute_set')

    # Build a dict: {type_name: [value1, value2, ...]}
    type_values = {}
    for pvt in variant_types:
        values = VariantAttribute.objects.filter(
            variant__product=product,
            variant_type=pvt.variant_type
        ).values_list('value', flat=True).distinct()
        type_values[pvt.variant_type.name] = list(values)

    variants = ProductVariant.objects.filter(
        product=product).prefetch_related('attributes__variant_type')

    from stock.models import StockLevel
    # Attach stock to each variant
    variant_data = []
    for v in variants:
        sl = StockLevel.objects.filter(
            product=product, variant=v, shop=shop).first()
        variant_data.append({
            'variant': v,
            'stock': sl.quantity if sl else 0,
            'attrs': {a.variant_type.name: a.value for a in v.attributes.all()},
        })

    return render(request, 'products/variants.html', {
        'product': product,
        'variant_types': variant_types,
        'type_values': type_values,
        'variant_data': variant_data,
        'shop': shop,
    })


@login_required
@require_POST
def add_variant_type(request, product_pk):
    """Add a new variant type to a product (e.g. 'Color')."""
    shop = get_current_shop(request)
    product = get_object_or_404(Product, pk=product_pk, shop=shop)
    type_name = request.POST.get('type_name', '').strip().title()
    if not type_name:
        messages.error(request, 'Variant type name is required.')
        return redirect('products:variants', product_pk=product_pk)
    vtype, _ = VariantType.objects.get_or_create(name=type_name)
    _, created = ProductVariantType.objects.get_or_create(
        product=product, variant_type=vtype)
    if created:
        product.has_variants = True
        product.save(update_fields=['has_variants'])
        messages.success(request, f'Variant type "{type_name}" added.')
    else:
        messages.info(request, f'"{type_name}" already exists on this product.')
    return redirect('products:variants', product_pk=product_pk)


@login_required
@require_POST
def add_variant_value(request, product_pk):
    """Add a specific value under an existing variant type (e.g. 'Black' under 'Color')."""
    shop = get_current_shop(request)
    product = get_object_or_404(Product, pk=product_pk, shop=shop)
    type_name = request.POST.get('type_name', '').strip()
    value = request.POST.get('value', '').strip()
    selling_price = request.POST.get('selling_price', '').strip() or None
    buying_price = request.POST.get('buying_price', '').strip() or None
    initial_stock = int(request.POST.get('initial_stock', 0) or 0)

    if not type_name or not value:
        messages.error(request, 'Both variant type and value are required.')
        return redirect('products:variants', product_pk=product_pk)

    vtype = get_object_or_404(VariantType, name=type_name)
    # Ensure this type is registered on the product
    ProductVariantType.objects.get_or_create(product=product, variant_type=vtype)

    # Check if a variant with this exact value already exists
    existing = VariantAttribute.objects.filter(
        variant__product=product, variant_type=vtype, value__iexact=value
    ).first()
    if existing:
        messages.warning(request, f'"{value}" already exists under {type_name}.')
        return redirect('products:variants', product_pk=product_pk)

    with transaction.atomic():
        variant = ProductVariant.objects.create(
            product=product,
            selling_price=selling_price,
            buying_price=buying_price,
        )
        VariantAttribute.objects.create(
            variant=variant, variant_type=vtype, value=value)

        # Set initial stock
        if initial_stock > 0:
            from stock.models import StockLevel, StockMovement
            sl, _ = StockLevel.objects.get_or_create(
                product=product, variant=variant, shop=shop,
                defaults={'quantity': 0}
            )
            sl.quantity += initial_stock
            sl.save()
            StockMovement.objects.create(
                product=product, variant=variant, shop=shop,
                movement_type='opening',
                quantity=initial_stock,
                quantity_before=0,
                quantity_after=initial_stock,
                created_by=request.user,
            )

    messages.success(request,
        f'Variant "{type_name}: {value}" added'
        + (f' with {initial_stock} units stock.' if initial_stock > 0 else '.'))
    return redirect('products:variants', product_pk=product_pk)


@login_required
@require_POST
def edit_variant(request, product_pk, variant_pk):
    """Edit price and stock of an existing variant."""
    shop = get_current_shop(request)
    product = get_object_or_404(Product, pk=product_pk, shop=shop)
    variant = get_object_or_404(ProductVariant, pk=variant_pk, product=product)

    selling_price = request.POST.get('selling_price', '').strip() or None
    buying_price  = request.POST.get('buying_price', '').strip() or None
    is_active     = request.POST.get('is_active') == 'on'
    new_stock     = request.POST.get('stock', '').strip()

    variant.selling_price = selling_price
    variant.buying_price  = buying_price
    variant.is_active     = is_active
    variant.save()

    if new_stock != '':
        from stock.models import StockLevel, StockMovement
        sl, _ = StockLevel.objects.get_or_create(
            product=product, variant=variant, shop=shop,
            defaults={'quantity': 0}
        )
        new_qty = int(new_stock)
        if new_qty != sl.quantity:
            old_qty = sl.quantity
            sl.quantity = new_qty
            sl.save()
            StockMovement.objects.create(
                product=product, variant=variant, shop=shop,
                movement_type='adjustment',
                quantity=new_qty - old_qty,
                quantity_before=old_qty,
                quantity_after=new_qty,
                created_by=request.user,
            )

    messages.success(request, 'Variant updated.')
    return redirect('products:variants', product_pk=product_pk)


@login_required
@require_POST
def delete_variant(request, product_pk, variant_pk):
    """Soft-delete (deactivate) a variant."""
    shop = get_current_shop(request)
    product = get_object_or_404(Product, pk=product_pk, shop=shop)
    variant = get_object_or_404(ProductVariant, pk=variant_pk, product=product)
    variant.is_active = False
    variant.save()
    messages.success(request, 'Variant deactivated.')
    return redirect('products:variants', product_pk=product_pk)


@login_required
@require_POST
def delete_variant_type(request, product_pk):
    """Remove an entire variant type and all its values from a product."""
    shop = get_current_shop(request)
    product = get_object_or_404(Product, pk=product_pk, shop=shop)
    type_name = request.POST.get('type_name', '').strip()
    try:
        vtype = VariantType.objects.get(name=type_name)
        ProductVariantType.objects.filter(product=product, variant_type=vtype).delete()
        # Deactivate variants that only have this type
        for v in ProductVariant.objects.filter(product=product):
            if v.attributes.count() == 0:
                v.is_active = False
                v.save()
        messages.success(request, f'Variant type "{type_name}" removed.')
    except VariantType.DoesNotExist:
        messages.error(request, 'Variant type not found.')
    return redirect('products:variants', product_pk=product_pk)


# ── BULK UPLOAD ─────────────────────────────────────────────────────────

@login_required
def bulk_upload(request):
    shop = get_current_shop(request)
    if not shop:
        return redirect('shop_select')

    result = None
    if request.method == 'POST' and request.FILES.get('upload_file'):
        f = request.FILES['upload_file']
        name = f.name.lower()
        from .bulk_upload import process_csv, process_excel

        if name.endswith('.csv'):
            result = process_csv(f, shop)
        elif name.endswith('.xlsx') or name.endswith('.xls'):
            result = process_excel(f, shop)
        else:
            messages.error(request, 'Unsupported file type. Please upload a .csv or .xlsx file.')
            return redirect('products:bulk_upload')

        if result['created'] > 0:
            messages.success(request, f"{result['created']} product(s) imported successfully.")
        if result['skipped'] > 0:
            messages.warning(request, f"{result['skipped']} row(s) skipped.")

    return render(request, 'products/bulk_upload.html', {
        'shop': shop, 'result': result
    })


# ── BULK UPLOAD ─────────────────────────────────────────────────

@login_required
def bulk_upload(request):
    shop = get_current_shop(request)
    if not shop:
        return redirect('shop_select')

    results = []
    errors  = []
    processed = False

    if request.method == 'POST':
        upload_file = request.FILES.get('upload_file')
        if not upload_file:
            messages.error(request, 'Please select a file to upload.')
        else:
            from .bulk_upload import process_csv, process_excel
            fname = upload_file.name.lower()
            if fname.endswith('.csv'):
                results, errors = process_csv(upload_file, shop, request.user)
            elif fname.endswith('.xlsx') or fname.endswith('.xls'):
                results, errors = process_excel(upload_file, shop, request.user)
            else:
                messages.error(request, 'Unsupported file type. Please upload a .csv or .xlsx file.')
                return render(request, 'products/bulk_upload.html', {'shop': shop})

            processed = True
            created_count = sum(1 for r in results if r['created'])
            updated_count = sum(1 for r in results if not r['created'])
            if results:
                messages.success(request,
                    f'Upload complete: {created_count} new product(s) created, '
                    f'{updated_count} updated. {len(errors)} error(s).')
            elif errors:
                messages.error(request, f'Upload failed with {len(errors)} error(s).')

    return render(request, 'products/bulk_upload.html', {
        'shop': shop,
        'results': results,
        'errors': errors,
        'processed': processed,
    })


@login_required
@require_POST
def save_price_tier(request, pk):
    shop = get_current_shop(request)
    product = get_object_or_404(Product, pk=pk, shop=shop)
    variant_id = request.POST.get('variant_id') or None
    variant = get_object_or_404(ProductVariant, pk=variant_id, product=product) if variant_id else None
    try:
        min_qty   = int(request.POST.get('min_quantity', 0))
        unit_price = Decimal(str(request.POST.get('unit_price', 0)))
    except Exception:
        messages.error(request, 'Invalid tier data.')
        return redirect('products:detail', pk=pk)
    if min_qty < 1 or unit_price <= 0:
        messages.error(request, 'Min quantity must be ≥ 1 and price must be > 0.')
        return redirect('products:detail', pk=pk)
    tier_id = request.POST.get('tier_id')
    if tier_id:
        tier = get_object_or_404(ProductPriceTier, pk=tier_id, product=product)
        tier.min_quantity = min_qty
        tier.unit_price   = unit_price
        tier.save()
        messages.success(request, 'Price tier updated.')
    else:
        ProductPriceTier.objects.update_or_create(
            product=product, variant=variant, min_quantity=min_qty,
            defaults={'unit_price': unit_price},
        )
        messages.success(request, 'Price tier added.')
    return redirect('products:detail', pk=pk)


@login_required
@require_POST
def delete_price_tier(request, pk, tier_pk):
    shop = get_current_shop(request)
    product = get_object_or_404(Product, pk=pk, shop=shop)
    tier = get_object_or_404(ProductPriceTier, pk=tier_pk, product=product)
    tier.delete()
    messages.success(request, 'Price tier removed.')
    return redirect('products:detail', pk=pk)


@login_required
def download_template(request):
    from django.http import HttpResponse
    from .bulk_upload import generate_template_csv
    csv_content = generate_template_csv()
    response = HttpResponse(csv_content, content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="proto_v3_product_template.csv"'
    return response
