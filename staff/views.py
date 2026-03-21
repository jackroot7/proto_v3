from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from shops.models import Shop, UserShopAccess
from .models import StaffProfile, AttendanceRecord, DisciplinaryRecord
from .forms import StaffCreateForm, DisciplinaryForm


def get_current_shop(request):
    shop_id = request.session.get('current_shop_id')
    return Shop.objects.filter(id=shop_id).first() if shop_id else None


@login_required
def staff_list(request):
    shop = get_current_shop(request)
    if not shop:
        return redirect('shop_select')
    staff = StaffProfile.objects.filter(shop=shop).select_related('user')
    return render(request, 'staff/list.html', {'staff': staff, 'shop': shop})


@login_required
def staff_create(request):
    shop = get_current_shop(request)
    role = request.session.get('current_role')
    if role not in ('owner', 'admin'):
        messages.error(request, 'Permission denied.')
        return redirect('staff:list')
    if request.method == 'POST':
        form = StaffCreateForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'],
                first_name=form.cleaned_data['first_name'],
                last_name=form.cleaned_data['last_name'],
            )
            profile = StaffProfile.objects.create(
                user=user,
                shop=shop,
                role=form.cleaned_data['role'],
                phone=form.cleaned_data['phone'],
                hire_date=form.cleaned_data['hire_date'],
                monthly_salary=form.cleaned_data['monthly_salary'],
            )
            UserShopAccess.objects.create(user=user, shop=shop, role=form.cleaned_data['role'])
            messages.success(request, f'Staff member {user.get_full_name()} added.')
            return redirect('staff:list')
    else:
        form = StaffCreateForm()
    return render(request, 'staff/form.html', {'form': form, 'shop': shop})


@login_required
def staff_detail(request, pk):
    shop = get_current_shop(request)
    member = get_object_or_404(StaffProfile, pk=pk, shop=shop)
    disciplinary = DisciplinaryRecord.objects.filter(staff=member).order_by('-incident_date')
    attendance = AttendanceRecord.objects.filter(staff=member).order_by('-date')[:30]
    return render(request, 'staff/detail.html', {
        'member': member, 'disciplinary': disciplinary,
        'attendance': attendance, 'shop': shop,
    })


@login_required
def add_disciplinary(request, pk):
    shop = get_current_shop(request)
    member = get_object_or_404(StaffProfile, pk=pk, shop=shop)
    if request.method == 'POST':
        form = DisciplinaryForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.staff = member
            record.recorded_by = request.user
            record.save()
            messages.success(request, 'Disciplinary record added.')
            return redirect('staff:detail', pk=pk)
    else:
        form = DisciplinaryForm()
    return render(request, 'staff/disciplinary_form.html', {'form': form, 'member': member})
