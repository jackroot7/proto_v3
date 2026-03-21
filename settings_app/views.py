from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import translation
from shops.models import Shop
from .models import ShopSettings
from .forms import ShopSettingsForm


def get_current_shop(request):
    shop_id = request.session.get('current_shop_id')
    return Shop.objects.filter(id=shop_id).first() if shop_id else None


def apply_language(request, lang):
    """Activate language - Django 4+ compatible (no LANGUAGE_SESSION_KEY)."""
    if lang in ('sw', 'en'):
        translation.activate(lang)
        request.session['django_language'] = lang


@login_required
def settings_index(request):
    shop = get_current_shop(request)
    if not shop:
        return redirect('shop_select')

    role = request.session.get('current_role', 'cashier')
    if role not in ('owner', 'admin'):
        messages.error(request, 'Only owners and admins can access settings.')
        return redirect('dashboard')

    settings_obj, _ = ShopSettings.objects.get_or_create(
        shop=shop,
        defaults={'tax_rate': 18.00, 'low_stock_threshold': 10}
    )

    if request.method == 'POST':
        form = ShopSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            saved = form.save()
            apply_language(request, saved.language)
            messages.success(request, 'Settings saved successfully.')
            return redirect('settings:index')
        else:
            messages.error(request, 'Please fix the errors below.')
    else:
        form = ShopSettingsForm(instance=settings_obj)

    from sync_engine.models import SyncQueue, SyncLog
    from pos.models import Sale
    from django.db.models import Sum
    from django.utils import timezone
    today = timezone.now().date()
    total_today = Sale.objects.filter(
        shop=shop, created_at__date=today, status='completed'
    ).aggregate(t=Sum('total'))['t'] or 0
    pending_sync = SyncQueue.objects.filter(status='pending').count()
    last_sync = SyncLog.objects.order_by('-created_at').first()

    return render(request, 'settings_app/index.html', {
        'shop': shop,
        'form': form,
        'settings': settings_obj,
        'pending_sync': pending_sync,
        'last_sync': last_sync,
        'total_today': total_today,
        'role': role,
        # Pass field groups explicitly for clean template rendering
        'general_fields': ['currency', 'timezone'],
        'tax_fields':     ['tax_name', 'tax_rate', 'tax_inclusive'],
        'pos_fields':     ['require_customer_on_credit', 'allow_negative_stock',
                           'print_receipt_auto', 'low_stock_threshold', 'auto_reorder'],
        'report_fields':  ['daily_report_enabled', 'daily_report_time',
                           'daily_report_email', 'daily_report_whatsapp'],
        'receipt_fields': ['receipt_header', 'receipt_footer', 'show_tax_on_receipt'],
    })


@login_required
def change_language(request):
    if request.method == 'POST':
        lang = request.POST.get('language', 'sw')
        apply_language(request, lang)
        shop = get_current_shop(request)
        if shop:
            obj, _ = ShopSettings.objects.get_or_create(shop=shop)
            obj.language = lang
            obj.save(update_fields=['language'])
    return redirect(request.POST.get('next', request.META.get('HTTP_REFERER', '/')))
