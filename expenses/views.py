from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum
from shops.models import Shop
from .models import Expense, ExpenseCategory
from .forms import ExpenseForm


def get_current_shop(request):
    shop_id = request.session.get('current_shop_id')
    return Shop.objects.filter(id=shop_id).first() if shop_id else None


@login_required
def expense_list(request):
    shop = get_current_shop(request)
    if not shop:
        return redirect('shop_select')

    today = timezone.now().date()
    first_of_month = today.replace(day=1)
    first_of_year = today.replace(month=1, day=1)

    from django.core.paginator import Paginator
    expenses_qs = Expense.objects.filter(shop=shop).select_related('category', 'recorded_by').order_by('-date')

    period = request.GET.get('period', 'month')
    if period == 'today':
        expenses_qs = expenses_qs.filter(date=today)
    elif period == 'month':
        expenses_qs = expenses_qs.filter(date__gte=first_of_month)
    elif period == 'year':
        expenses_qs = expenses_qs.filter(date__gte=first_of_year)
    paginator = Paginator(expenses_qs, 25)
    expenses  = paginator.get_page(request.GET.get('page'))
    page_obj  = expenses

    total_today = Expense.objects.filter(shop=shop, date=today).aggregate(t=Sum('amount'))['t'] or 0
    total_month = Expense.objects.filter(shop=shop, date__gte=first_of_month).aggregate(t=Sum('amount'))['t'] or 0
    total_year = Expense.objects.filter(shop=shop, date__gte=first_of_year).aggregate(t=Sum('amount'))['t'] or 0

    by_category = Expense.objects.filter(shop=shop, date__gte=first_of_month).values(
        'category__name'
    ).annotate(total=Sum('amount')).order_by('-total')

    return render(request, 'expenses/list.html', {
        'expenses': expenses, 'page_obj': page_obj,
        'shop': shop,
        'total_today': total_today,
        'total_month': total_month,
        'total_year': total_year,
        'by_category': by_category,
        'period': period,
    })


@login_required
def expense_create(request):
    shop = get_current_shop(request)
    if not shop:
        return redirect('shop_select')
    if request.method == 'POST':
        form = ExpenseForm(request.POST, request.FILES)
        if form.is_valid():
            exp = form.save(commit=False)
            exp.shop = shop
            exp.recorded_by = request.user
            exp.save()
            messages.success(request, 'Expense recorded.')
            return redirect('expenses:list')
    else:
        form = ExpenseForm(initial={'date': timezone.now().date()})
    return render(request, 'expenses/form.html', {'form': form, 'shop': shop})
