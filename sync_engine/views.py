import time
import hmac
import hashlib
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils import timezone
from django.conf import settings as django_settings
from .models import SyncQueue, SyncLog


# ── STATUS ────────────────────────────────────────────────────────
@login_required
def sync_status(request):
    pending  = SyncQueue.objects.filter(status='pending').count()
    failed   = SyncQueue.objects.filter(status='failed').count()
    last_log = SyncLog.objects.order_by('-created_at').first()
    configured = bool(getattr(django_settings, 'CLOUD_SYNC_URL', ''))
    return JsonResponse({
        'pending':    pending,
        'failed':     failed,
        'last_sync':  last_log.created_at.isoformat() if last_log else None,
        'online':     True,
        'configured': configured,
    })


# ── SYNC DASHBOARD ─────────────────────────────────────────────────
@login_required
def sync_dashboard(request):
    from shops.models import Shop
    shop_id = request.session.get('current_shop_id')
    shop = Shop.objects.filter(id=shop_id).first()

    pending_items = SyncQueue.objects.filter(status='pending').order_by('created_at')[:50]
    failed_items  = SyncQueue.objects.filter(status='failed').order_by('-created_at')[:50]
    recent_logs   = SyncLog.objects.order_by('-created_at')[:20]

    total_pending = SyncQueue.objects.filter(status='pending').count()
    total_failed  = SyncQueue.objects.filter(status='failed').count()
    total_synced  = SyncQueue.objects.filter(status='synced').count()

    configured = bool(getattr(django_settings, 'CLOUD_SYNC_URL', ''))
    cloud_url  = getattr(django_settings, 'CLOUD_SYNC_URL', '')

    return render(request, 'sync_engine/dashboard.html', {
        'shop': shop,
        'pending_items': pending_items,
        'failed_items':  failed_items,
        'recent_logs':   recent_logs,
        'total_pending': total_pending,
        'total_failed':  total_failed,
        'total_synced':  total_synced,
        'configured':    configured,
        'cloud_url':     cloud_url,
    })


# ── CORE SYNC LOGIC (shared by trigger and background) ─────────────
def _do_sync(batch_size=None):
    """
    Upload pending records to the cloud server.
    Returns dict: {synced, failed, duration, error}
    """
    import requests as req_lib

    cloud_url  = getattr(django_settings, 'CLOUD_SYNC_URL', '').rstrip('/')
    api_key    = getattr(django_settings, 'CLOUD_SYNC_API_KEY', '')
    timeout    = getattr(django_settings, 'SYNC_TIMEOUT', 15)
    batch_size = batch_size or getattr(django_settings, 'SYNC_BATCH_SIZE', 50)
    max_retry  = getattr(django_settings, 'SYNC_MAX_RETRIES', 3)

    if not cloud_url:
        return {'synced': 0, 'failed': 0, 'duration': 0,
                'error': 'CLOUD_SYNC_URL not configured'}
    if not api_key:
        return {'synced': 0, 'failed': 0, 'duration': 0,
                'error': 'CLOUD_SYNC_API_KEY not configured'}

    start  = time.time()
    synced = 0
    failed = 0

    pending = SyncQueue.objects.filter(
        status__in=['pending', 'failed'],
        attempts__lt=max_retry,
    ).order_by('created_at')[:batch_size]

    for item in pending:
        try:
            payload_bytes = json.dumps(item.payload, sort_keys=True).encode()
            signature = hmac.new(
                api_key.encode(), payload_bytes, hashlib.sha256
            ).hexdigest()

            response = req_lib.post(
                f'{cloud_url}/sync/receive/',
                json={
                    'payload':       item.payload,
                    'shop_id':       item.payload.get('shop_id'),
                    'model':         item.payload.get('model', ''),
                    'operation':     item.operation,
                    'local_id':      item.object_id,
                    'content_type':  str(item.content_type),
                },
                headers={
                    'X-Sync-Api-Key':   api_key,
                    'X-Sync-Signature': signature,
                    'Content-Type':     'application/json',
                },
                timeout=timeout,
            )

            if response.status_code in (200, 201):
                item.status        = 'synced'
                item.synced_at     = timezone.now()
                item.error_message = ''
                item.save(update_fields=['status', 'synced_at', 'error_message', 'attempts'])
                synced += 1
            else:
                raise Exception(f'HTTP {response.status_code}: {response.text[:200]}')

        except Exception as e:
            item.status        = 'failed'
            item.attempts     += 1
            item.error_message = str(e)[:500]
            item.save(update_fields=['status', 'attempts', 'error_message'])
            failed += 1

    duration = round(time.time() - start, 2)

    if synced or failed:
        SyncLog.objects.create(
            direction='up',
            records_synced=synced,
            records_failed=failed,
            duration_seconds=duration,
        )

    return {'synced': synced, 'failed': failed, 'duration': duration, 'error': ''}


# ── MANUAL TRIGGER ─────────────────────────────────────────────────
@login_required
@require_POST
def trigger_sync(request):
    result = _do_sync()
    if result.get('error') and not result['synced']:
        return JsonResponse(result, status=400)
    result['pending'] = SyncQueue.objects.filter(status='pending').count()
    return JsonResponse(result)


# ── RETRY FAILED ───────────────────────────────────────────────────
@login_required
@require_POST
def retry_failed(request):
    count = SyncQueue.objects.filter(status='failed').update(
        status='pending', attempts=0, error_message=''
    )
    return JsonResponse({'reset': count, 'message': f'{count} item(s) reset to pending.'})


# ── CLEAR OLD SYNCED ───────────────────────────────────────────────
@login_required
@require_POST
def clear_synced(request):
    from datetime import timedelta
    cutoff = timezone.now() - timedelta(days=30)
    count, _ = SyncQueue.objects.filter(status='synced', synced_at__lt=cutoff).delete()
    return JsonResponse({'deleted': count, 'message': f'{count} old record(s) removed.'})


# ── PURGE ALL FAILED ───────────────────────────────────────────────
@login_required
@require_POST
def purge_failed(request):
    count, _ = SyncQueue.objects.filter(status='failed').delete()
    return JsonResponse({'deleted': count})


# ── RECEIVER ENDPOINT (runs on cloud server) ────────────────────────
@csrf_exempt
@require_POST
def receive_sync(request):
    """
    Cloud server endpoint. Local Proto v3 devices POST here.
    Deploy this app on your cloud Django project, set CLOUD_SYNC_API_KEY.
    """
    api_key = getattr(django_settings, 'CLOUD_SYNC_API_KEY', '')
    if not api_key:
        return JsonResponse({'error': 'Sync not configured on server'}, status=500)

    # Verify API key
    received_key = request.headers.get('X-Sync-Api-Key', '')
    if not hmac.compare_digest(received_key.encode(), api_key.encode()):
        return JsonResponse({'error': 'Unauthorised'}, status=401)

    # Parse body
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    # Verify HMAC signature
    received_sig = request.headers.get('X-Sync-Signature', '')
    payload_bytes = json.dumps(body.get('payload', {}), sort_keys=True).encode()
    expected_sig  = hmac.new(api_key.encode(), payload_bytes, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(received_sig, expected_sig):
        return JsonResponse({'error': 'Signature mismatch'}, status=401)

    payload   = body.get('payload', {})
    model     = payload.get('model', '')
    operation = body.get('operation', 'create')

    try:
        result = _apply_sync_payload(model, operation, payload)
        return JsonResponse({'status': 'ok', 'model': model, 'result': result})
    except Exception as e:
        return JsonResponse({'error': str(e), 'model': model}, status=422)


def _apply_sync_payload(model, operation, payload):
    from decimal import Decimal
    import datetime

    if model == 'Sale':
        from pos.models import Sale, SaleItem
        from shops.models import Shop
        from django.contrib.auth.models import User

        shop = Shop.objects.filter(id=payload['shop_id']).first()
        if not shop:
            raise Exception(f"Shop {payload['shop_id']} not found")

        cashier, _ = User.objects.get_or_create(
            username=payload.get('cashier_username', 'synced_user'),
            defaults={'first_name': 'Synced'}
        )

        sale, created = Sale.objects.update_or_create(
            sale_number=payload['sale_number'],
            defaults={
                'shop': shop, 'cashier': cashier,
                'subtotal':       Decimal(str(payload['subtotal'])),
                'tax_amount':     Decimal(str(payload['tax_amount'])),
                'total':          Decimal(str(payload['total'])),
                'payment_method': payload['payment_method'],
                'amount_paid':    Decimal(str(payload['amount_paid'])),
                'change_given':   Decimal(str(payload['change_given'])),
                'status':         payload['status'],
            }
        )
        if created:
            for item in payload.get('items', []):
                from products.models import Product
                product = Product.objects.filter(id=item['product_id'], shop=shop).first()
                if product:
                    SaleItem.objects.create(
                        sale=sale, product=product,
                        quantity=item['quantity'],
                        unit_price=Decimal(str(item['unit_price'])),
                        buying_price=Decimal(str(item['buying_price'])),
                        line_total=Decimal(str(item['line_total'])),
                    )
        return 'created' if created else 'updated'

    elif model == 'Expense':
        from expenses.models import Expense, ExpenseCategory
        from shops.models import Shop
        shop = Shop.objects.filter(id=payload['shop_id']).first()
        if not shop:
            raise Exception(f"Shop {payload['shop_id']} not found")
        cat = None
        if payload.get('category_name'):
            cat, _ = ExpenseCategory.objects.get_or_create(name=payload['category_name'])
        Expense.objects.create(
            shop=shop, category=cat,
            amount=Decimal(str(payload['amount'])),
            description=payload.get('description', ''),
            date=datetime.date.fromisoformat(payload['date']),
        )
        return 'created'

    elif model == 'StockMovement':
        from stock.models import StockMovement
        from products.models import Product
        from shops.models import Shop
        shop    = Shop.objects.filter(id=payload['shop_id']).first()
        product = Product.objects.filter(id=payload['product_id']).first()
        if not shop or not product:
            raise Exception('Shop or product not found')
        StockMovement.objects.create(
            shop=shop, product=product,
            movement_type=payload['movement_type'],
            quantity=payload['quantity'],
            quantity_before=payload['quantity_before'],
            quantity_after=payload['quantity_after'],
            reference=payload.get('reference', ''),
            notes=payload.get('notes', ''),
        )
        return 'created'

    elif model == 'Customer':
        from customers.models import Customer
        from shops.models import Shop
        shop = Shop.objects.filter(id=payload['shop_id']).first()
        if not shop:
            raise Exception(f"Shop {payload['shop_id']} not found")
        Customer.objects.update_or_create(
            shop=shop, name=payload['name'],
            defaults={
                'phone':          payload.get('phone', ''),
                'email':          payload.get('email', ''),
                'credit_balance': Decimal(str(payload.get('credit_balance', 0))),
            }
        )
        return 'upserted'

    elif model == 'DaySession':
        from shops.models import Shop, DaySession
        shop = Shop.objects.filter(id=payload['shop_id']).first()
        if not shop:
            raise Exception(f"Shop {payload['shop_id']} not found")
        DaySession.objects.update_or_create(
            shop=shop,
            date=datetime.date.fromisoformat(payload['date']),
            defaults={
                'status':             payload['status'],
                'opening_cash':       Decimal(str(payload.get('opening_cash', 0))),
                'closing_cash':       Decimal(str(payload.get('closing_cash', 0))),
                'total_sales':        Decimal(str(payload.get('total_sales', 0))),
                'total_cash':         Decimal(str(payload.get('total_cash', 0))),
                'total_mpesa':        Decimal(str(payload.get('total_mpesa', 0))),
                'total_credit':       Decimal(str(payload.get('total_credit', 0))),
                'total_transactions': payload.get('total_transactions', 0),
            }
        )
        return 'upserted'

    elif model == 'PurchaseOrder':
        # Cloud records purchase orders for auditing
        return 'noted'

    else:
        return f'unknown model {model!r} — skipped'
    

    