from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from shops.models import Shop
from .models import Customer, CreditPayment
from .forms import CustomerForm, CreditPaymentForm


def get_current_shop(request):
    shop_id = request.session.get('current_shop_id')
    return Shop.objects.filter(id=shop_id).first() if shop_id else None


@login_required
def customer_list(request):
    shop = get_current_shop(request)
    if not shop:
        return redirect('shop_select')
    from django.core.paginator import Paginator
    customers = Customer.objects.filter(shop=shop, is_active=True)
    search = request.GET.get('q', '')
    if search:
        customers = customers.filter(name__icontains=search)
    filter_debt = request.GET.get('debt', '')
    if filter_debt:
        customers = customers.filter(credit_balance__gt=0)
    paginator = Paginator(customers.order_by('name'), 25)
    page_obj  = paginator.get_page(request.GET.get('page'))
    return render(request, 'customers/list.html', {
        'customers': page_obj, 'page_obj': page_obj, 'shop': shop, 'search': search,
    })


@login_required
def customer_detail(request, pk):
    shop = get_current_shop(request)
    customer = get_object_or_404(Customer, pk=pk, shop=shop)
    sales = customer.sales.filter(shop=shop).order_by('-created_at')[:20]
    payments = CreditPayment.objects.filter(customer=customer).order_by('-created_at')
    return render(request, 'customers/detail.html', {
        'customer': customer, 'sales': sales, 'payments': payments, 'shop': shop,
    })


@login_required
def customer_create(request):
    shop = get_current_shop(request)
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            c = form.save(commit=False)
            c.shop = shop
            c.save()
            messages.success(request, f'Customer {c.name} added.')
            return redirect('customers:list')
    else:
        form = CustomerForm()
    return render(request, 'customers/form.html', {'form': form, 'shop': shop})


@login_required
def record_credit_payment(request, pk):
    shop = get_current_shop(request)
    customer = get_object_or_404(Customer, pk=pk, shop=shop)

    if request.method == 'POST':
        form = CreditPaymentForm(request.POST, max_amount=customer.credit_balance)
        if form.is_valid():
            amount = form.cleaned_data['amount']

            # Validate: payment cannot exceed what is actually owed
            if amount > customer.credit_balance:
                form.add_error(
                    'amount',
                    f'Payment of TSh {amount:,.0f} exceeds the outstanding balance of '
                    f'TSh {customer.credit_balance:,.0f}. '
                    f'Maximum payable is TSh {customer.credit_balance:,.0f}.'
                )
            else:
                payment = form.save(commit=False)
                payment.customer = customer
                payment.save()
                customer.credit_balance -= amount
                customer.save(update_fields=['credit_balance'])
                messages.success(
                    request,
                    f'Payment of TSh {amount:,.0f} recorded. '
                    f'Remaining balance: TSh {customer.credit_balance:,.0f}.'
                )
                return redirect('customers:detail', pk=pk)
    else:
        form = CreditPaymentForm(max_amount=customer.credit_balance)

    return render(request, 'customers/credit_payment.html', {
        'form': form, 'customer': customer, 'shop': shop,
    })
