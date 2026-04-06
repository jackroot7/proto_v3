from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.db import models
from .models import Shop, UserShopAccess, DaySession
from .forms import LoginForm


def login_view(request):
    if request.user.is_authenticated:
        return redirect('shop_select')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            user = authenticate(
                request,
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password']
            )
            if user and user.is_active:
                login(request, user)
                return redirect('shop_select')
            else:
                messages.error(request, 'Invalid username or password.')
    else:
        form = LoginForm()

    return render(request, 'shops/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def shop_select(request):
    """After login, user selects which shop to enter."""
    accessible = UserShopAccess.objects.filter(
        user=request.user, is_active=True
    ).select_related('shop')

    if not accessible.exists():
        messages.error(request, 'You have no shop access. Contact the owner.')
        logout(request)
        return redirect('login')

    if request.method == 'POST':
        shop_id = request.POST.get('shop_id')
        access = get_object_or_404(UserShopAccess, user=request.user, shop_id=shop_id, is_active=True)
        request.session['current_shop_id'] = access.shop.id
        request.session['current_shop_name'] = access.shop.name
        request.session['current_role'] = access.role
        return redirect('dashboard')

    return render(request, 'shops/shop_select.html', {
        'accessible_shops': accessible
    })


@login_required
def switch_shop(request):
    """Switch current active shop mid-session."""
    if request.method == 'POST':
        shop_id = request.POST.get('shop_id')
        try:
            access = UserShopAccess.objects.get(user=request.user, shop_id=shop_id, is_active=True)
            request.session['current_shop_id'] = access.shop.id
            request.session['current_shop_name'] = access.shop.name
            request.session['current_role'] = access.role
        except UserShopAccess.DoesNotExist:
            messages.error(request, 'You do not have access to that shop.')
    return redirect(request.POST.get('next', 'dashboard'))


@login_required
def dashboard(request):
    from pos.models import Sale, SaleItem
    from stock.models import StockLevel
    from expenses.models import Expense
    from customers.models import Customer
    from django.db.models import Sum, Count, Avg
    from decimal import Decimal
    import datetime

    shop_id = request.session.get('current_shop_id')
    if not shop_id:
        return redirect('shop_select')

    shop = get_object_or_404(Shop, id=shop_id)
    today = timezone.now().date()
    yesterday = today - datetime.timedelta(days=1)
    first_of_month = today.replace(day=1)
    first_of_last_month = (today.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
    last_month_end = today.replace(day=1) - datetime.timedelta(days=1)

    # ── Day session ──────────────────────────────────────────────
    day_session = DaySession.objects.filter(shop=shop, date=today).first()

    # ── Today's sales ────────────────────────────────────────────
    today_qs = Sale.objects.filter(shop=shop, created_at__date=today, status='completed')
    total_sales    = today_qs.aggregate(t=Sum('total'))['t'] or Decimal('0')
    total_tax      = today_qs.aggregate(t=Sum('tax_amount'))['t'] or Decimal('0')
    txn_count      = today_qs.count()

    # Profit: sum of (unit_price - buying_price) * qty for all items today
    today_items = SaleItem.objects.filter(sale__in=today_qs)
    total_profit = sum(
        (item.unit_price - item.buying_price) * item.quantity
        for item in today_items
    )

    # ── Yesterday comparison ─────────────────────────────────────
    yesterday_qs    = Sale.objects.filter(shop=shop, created_at__date=yesterday, status='completed')
    yesterday_sales = yesterday_qs.aggregate(t=Sum('total'))['t'] or Decimal('0')
    yesterday_txns  = yesterday_qs.count()

    def pct_change(today_val, yesterday_val):
        if yesterday_val and yesterday_val > 0:
            return round(((float(today_val) - float(yesterday_val)) / float(yesterday_val)) * 100, 1)
        return None

    sales_change = pct_change(total_sales, yesterday_sales)
    txn_change   = pct_change(txn_count, yesterday_txns)

    # ── This month ───────────────────────────────────────────────
    month_qs           = Sale.objects.filter(shop=shop, created_at__date__gte=first_of_month, status='completed')
    monthly_revenue    = month_qs.aggregate(t=Sum('total'))['t'] or Decimal('0')
    monthly_txns       = month_qs.count()
    monthly_expenses   = Expense.objects.filter(shop=shop, date__gte=first_of_month).aggregate(t=Sum('amount'))['t'] or Decimal('0')
    month_items        = SaleItem.objects.filter(sale__in=month_qs)
    monthly_cogs       = sum((i.buying_price * i.quantity) for i in month_items)
    monthly_gross      = float(monthly_revenue) - float(monthly_cogs)
    monthly_net        = monthly_gross - float(monthly_expenses)

    # ── Last month comparison ─────────────────────────────────────
    last_month_qs      = Sale.objects.filter(shop=shop, created_at__date__range=(first_of_last_month, last_month_end), status='completed')
    last_month_revenue = last_month_qs.aggregate(t=Sum('total'))['t'] or Decimal('0')
    revenue_change     = pct_change(monthly_revenue, last_month_revenue)

    # ── Payment breakdown today ──────────────────────────────────
    cash_total   = today_qs.filter(payment_method='cash').aggregate(t=Sum('total'))['t'] or Decimal('0')
    mpesa_total  = today_qs.filter(payment_method='mpesa').aggregate(t=Sum('total'))['t'] or Decimal('0')
    credit_total = today_qs.filter(payment_method='credit').aggregate(t=Sum('total'))['t'] or Decimal('0')

    # ── Stock alerts ─────────────────────────────────────────────
    low_stock_items = StockLevel.objects.filter(
        shop=shop,
        quantity__lte=models.F('product__low_stock_threshold')
    ).select_related('product', 'product__uom').order_by('quantity')[:6]

    out_of_stock_count = StockLevel.objects.filter(shop=shop, quantity__lte=0).count()
    low_stock_count    = StockLevel.objects.filter(
        shop=shop, quantity__gt=0,
        quantity__lte=models.F('product__low_stock_threshold')
    ).count()

    # ── Outstanding credit ───────────────────────────────────────
    credit_customers     = Customer.objects.filter(shop=shop, credit_balance__gt=0)
    total_credit_owed    = credit_customers.aggregate(t=Sum('credit_balance'))['t'] or Decimal('0')
    credit_customer_count = credit_customers.count()

    # ── Top products this month ──────────────────────────────────
    top_products = SaleItem.objects.filter(
        sale__shop=shop,
        sale__created_at__date__gte=first_of_month,
        sale__status='completed'
    ).values('product__name', 'product__uom__short_name').annotate(
        total_qty=Sum('quantity'),
        total_rev=Sum('line_total')
    ).order_by('-total_qty')[:6]

    # ── Weekly chart (last 7 days) ────────────────────────────────
    weekly_data = []
    for i in range(6, -1, -1):
        d = today - datetime.timedelta(days=i)
        day_total = Sale.objects.filter(
            shop=shop, created_at__date=d, status='completed'
        ).aggregate(t=Sum('total'))['t'] or 0
        weekly_data.append({'date': d.strftime('%a'), 'total': float(day_total)})

    # ── Hourly sales today (for heatmap) ─────────────────────────
    hourly = [0] * 24
    for sale in today_qs.only('created_at'):
        hourly[sale.created_at.hour] += 1

    # ── Recent transactions ───────────────────────────────────────
    recent_sales = today_qs.select_related('customer', 'cashier').order_by('-created_at')[:5]

    # ── AI recommendations ────────────────────────────────────────
    recommendations = []
    for item in low_stock_items[:3]:
        recommendations.append({
            'type': 'restock',
            'title': f'Restock {item.product.name}',
            'body': f'Only {item.quantity} {"" if not item.product.uom else item.product.uom.short_name} remaining - below threshold of {item.product.low_stock_threshold}.',
            'color': '#9b2626',
            'bg': '#fdeaea',
        })
    if credit_customer_count > 0:
        recommendations.append({
            'type': 'credit',
            'title': f'Chase {credit_customer_count} credit customer{"s" if credit_customer_count > 1 else ""}',
            'body': f'Total outstanding: TSh {total_credit_owed:,.0f}.',
            'color': '#7a5010',
            'bg': '#fef3dc',
        })
    # Suggest promoting items with no sales this month
    from products.models import Product
    all_products = set(Product.objects.filter(shop=shop, is_active=True).values_list('id', flat=True))
    sold_products = set(
        SaleItem.objects.filter(
            sale__shop=shop, sale__created_at__date__gte=first_of_month, sale__status='completed'
        ).values_list('product_id', flat=True).distinct()
    )
    unsold = all_products - sold_products
    if unsold:
        unsold_names = Product.objects.filter(id__in=list(unsold)[:2]).values_list('name', flat=True)
        recommendations.append({
            'type': 'promote',
            'title': f'Promote slow movers',
            'body': f'{len(unsold)} product{"s" if len(unsold)>1 else ""} with no sales this month, e.g. {", ".join(unsold_names)}.',
            'color': '#0c447c',
            'bg': '#e6f1fb',
        })

    return render(request, 'shops/dashboard.html', {
        'shop': shop,
        'day_session': day_session,
        # Today
        'total_sales': total_sales,
        'total_profit': total_profit,
        'total_tax': total_tax,
        'txn_count': txn_count,
        'sales_change': sales_change,
        'txn_change': txn_change,
        # Month
        'monthly_revenue': monthly_revenue,
        'monthly_gross': monthly_gross,
        'monthly_net': monthly_net,
        'monthly_txns': monthly_txns,
        'monthly_expenses': monthly_expenses,
        'revenue_change': revenue_change,
        # Payments
        'cash_total': cash_total,
        'mpesa_total': mpesa_total,
        'credit_total': credit_total,
        # Stock
        'low_stock_items': low_stock_items,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        # Credit
        'total_credit_owed': total_credit_owed,
        'credit_customer_count': credit_customer_count,
        # Charts & lists
        'weekly_data': weekly_data,
        'hourly_data': hourly,
        'top_products': top_products,
        'recent_sales': recent_sales,
        'recommendations': recommendations,
    })


@login_required
def day_summary(request):
    """AJAX endpoint - returns today's summary for the close-day modal."""
    from pos.models import Sale, SaleItem
    from expenses.models import Expense
    from django.db.models import Sum
    from decimal import Decimal

    shop_id = request.session.get('current_shop_id')
    if not shop_id:
        from django.http import JsonResponse
        return JsonResponse({'error': 'No shop'}, status=400)

    shop = get_object_or_404(Shop, id=shop_id)
    today = timezone.now().date()

    today_qs = Sale.objects.filter(shop=shop, created_at__date=today, status='completed')
    total    = today_qs.aggregate(t=Sum('total'))['t'] or Decimal('0')
    cash     = today_qs.filter(payment_method='cash').aggregate(t=Sum('total'))['t'] or Decimal('0')
    mpesa    = today_qs.filter(payment_method='mpesa').aggregate(t=Sum('total'))['t'] or Decimal('0')
    credit   = today_qs.filter(payment_method='credit').aggregate(t=Sum('total'))['t'] or Decimal('0')
    tax      = today_qs.aggregate(t=Sum('tax_amount'))['t'] or Decimal('0')
    txns     = today_qs.count()

    # Profit
    items = SaleItem.objects.filter(sale__in=today_qs)
    profit = sum((i.unit_price - i.buying_price) * i.quantity for i in items)

    expenses = Expense.objects.filter(shop=shop, date=today).aggregate(t=Sum('amount'))['t'] or Decimal('0')

    session = DaySession.objects.filter(shop=shop, date=today).first()
    opening_cash = session.opening_cash if session else 0

    from django.http import JsonResponse
    return JsonResponse({
        'total':        str(total),
        'cash':         str(cash),
        'mpesa':        str(mpesa),
        'credit':       str(credit),
        'tax':          str(tax),
        'txns':         txns,
        'profit':       str(profit),
        'expenses':     str(expenses),
        'opening_cash': str(opening_cash),
    })


@login_required
def open_day(request):
    if request.method == 'POST':
        shop_id = request.session.get('current_shop_id')
        shop = get_object_or_404(Shop, id=shop_id)
        today = timezone.now().date()

        session, created = DaySession.objects.get_or_create(
            shop=shop,
            date=today,
            defaults={
                'opened_by': request.user,
                'opening_cash': request.POST.get('opening_cash', 0),
                'status': 'open',
            }
        )
        if not created and session.status == 'closed':
            messages.error(request, 'Day was already closed. Contact the owner.')
            return redirect('dashboard')

        messages.success(request, f'Day opened successfully for {shop.name}.')
        return redirect('pos:index')

    return redirect('dashboard')


@login_required
def close_day(request):
    if request.method == 'POST':
        shop_id = request.session.get('current_shop_id')
        shop = get_object_or_404(Shop, id=shop_id)
        today = timezone.now().date()
        session = get_object_or_404(DaySession, shop=shop, date=today, status='open')

        from pos.models import Sale
        from django.db.models import Sum
        today_sales = Sale.objects.filter(shop=shop, created_at__date=today, status='completed')

        session.status = 'closed'
        session.closed_by = request.user
        session.closed_at = timezone.now()
        session.closing_cash = request.POST.get('closing_cash', 0)
        session.total_sales = today_sales.aggregate(t=Sum('total'))['t'] or 0
        session.total_cash = today_sales.filter(payment_method='cash').aggregate(t=Sum('total'))['t'] or 0
        session.total_mpesa = today_sales.filter(payment_method='mpesa').aggregate(t=Sum('total'))['t'] or 0
        session.total_credit = today_sales.filter(payment_method='credit').aggregate(t=Sum('total'))['t'] or 0
        session.total_transactions = today_sales.count()
        session.save()

        # Trigger report generation and delivery
        from reports.utils import generate_daily_report, send_daily_report
        try:
            pdf_path = generate_daily_report(session)
            send_daily_report(session, pdf_path)
            session.report_sent = True
            session.save(update_fields=['report_sent'])
        except Exception:
            pass  # Fail silently - day is still closed

        messages.success(request, f'Day closed. Report will be sent to the owner.')
        return redirect('dashboard')

    return redirect('dashboard')
