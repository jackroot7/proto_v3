from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import UnitOfMeasure
from .forms import UOMForm


@login_required
def uom_list(request):
    units = UnitOfMeasure.objects.all()
    return render(request, 'units/list.html', {'units': units})


@login_required
def uom_create(request):
    if request.method == 'POST':
        form = UOMForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Unit of measure added.')
            return redirect('units:list')
    else:
        form = UOMForm()
    return render(request, 'units/form.html', {'form': form, 'action': 'Create'})


@login_required
def uom_edit(request, pk):
    unit = get_object_or_404(UnitOfMeasure, pk=pk)
    if request.method == 'POST':
        form = UOMForm(request.POST, instance=unit)
        if form.is_valid():
            form.save()
            messages.success(request, f'{unit.name} updated.')
            return redirect('units:list')
    else:
        form = UOMForm(instance=unit)
    return render(request, 'units/form.html', {'form': form, 'action': 'Edit', 'unit': unit})
