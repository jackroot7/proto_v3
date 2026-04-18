"""
Sync Engine Utilities
─────────────────────
queue_for_sync(instance, operation)  - add any model instance to the upload queue
build_payload(instance)              - serialise a model instance to a clean JSON dict
auto_sync_if_online()                - non-blocking background sync attempt
"""

import json
import threading
from decimal import Decimal
from django.contrib.contenttypes.models import ContentType
from .models import SyncQueue


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def build_payload(instance):
    model_name = instance.__class__.__name__

    if model_name == 'Sale':
        items = []
        for item in instance.items.select_related('product', 'variant').all():
            items.append({
                'product_id':   item.product_id,
                'product_name': item.product.name,
                'variant_id':   item.variant_id,
                'quantity':     item.quantity,
                'unit_price':   float(item.unit_price),
                'buying_price': float(item.buying_price),
                'line_total':   float(item.line_total),
            })
        return {
            'model':            'Sale',
            'sale_number':      instance.sale_number,
            'shop_id':          instance.shop_id,
            'shop_name':        instance.shop.name,
            'customer_id':      instance.customer_id,
            'customer_name':    instance.customer.name if instance.customer else None,
            'cashier_id':       instance.cashier_id,
            'cashier_username': instance.cashier.username if instance.cashier else None,
            'subtotal':         float(instance.subtotal),
            'tax_amount':       float(instance.tax_amount),
            'total':            float(instance.total),
            'payment_method':   instance.payment_method,
            'amount_paid':      float(instance.amount_paid),
            'change_given':     float(instance.change_given),
            'status':           instance.status,
            'created_at':       instance.created_at.isoformat(),
            'items':            items,
        }

    elif model_name == 'Expense':
        return {
            'model':         'Expense',
            'shop_id':       instance.shop_id,
            'shop_name':     instance.shop.name,
            'category_name': instance.category.name if instance.category else None,
            'amount':        float(instance.amount),
            'description':   instance.description,
            'date':          str(instance.date),
            'created_at':    instance.created_at.isoformat(),
        }

    elif model_name == 'StockMovement':
        return {
            'model':           'StockMovement',
            'shop_id':         instance.shop_id,
            'product_id':      instance.product_id,
            'product_name':    instance.product.name,
            'variant_id':      instance.variant_id,
            'movement_type':   instance.movement_type,
            'quantity':        instance.quantity,
            'quantity_before': instance.quantity_before,
            'quantity_after':  instance.quantity_after,
            'reference':       instance.reference,
            'notes':           instance.notes,
            'created_at':      instance.created_at.isoformat(),
        }

    elif model_name == 'Customer':
        return {
            'model':          'Customer',
            'shop_id':        instance.shop_id,
            'name':           instance.name,
            'phone':          instance.phone,
            'email':          instance.email,
            'credit_limit':   float(instance.credit_limit),
            'credit_balance': float(instance.credit_balance),
            'created_at':     instance.created_at.isoformat(),
        }

    elif model_name == 'DaySession':
        return {
            'model':              'DaySession',
            'shop_id':            instance.shop_id,
            'date':               str(instance.date),
            'status':             instance.status,
            'opening_cash':       float(instance.opening_cash or 0),
            'closing_cash':       float(instance.closing_cash or 0),
            'total_sales':        float(instance.total_sales or 0),
            'total_cash':         float(instance.total_cash or 0),
            'total_mpesa':        float(instance.total_mpesa or 0),
            'total_credit':       float(instance.total_credit or 0),
            'total_transactions': instance.total_transactions or 0,
        }

    elif model_name == 'StockLevel':
        return {
            'model':      'StockLevel',
            'shop_id':    instance.shop_id,
            'product_id': instance.product_id,
            'variant_id': instance.variant_id,
            'quantity':   instance.quantity,
        }

    elif model_name == 'PurchaseOrder':
        items = []
        for item in instance.items.select_related('product').all():
            items.append({
                'product_id':        item.product_id,
                'product_name':      item.product.name,
                'quantity_ordered':  item.quantity_ordered,
                'quantity_received': item.quantity_received,
                'unit_cost':         float(item.unit_cost),
                'line_total':        float(item.line_total),
            })
        return {
            'model':          'PurchaseOrder',
            'shop_id':        instance.shop_id,
            'order_number':   instance.order_number,
            'supplier_name':  instance.supplier.name,
            'status':         instance.status,
            'total':          float(instance.total),
            'order_date':     str(instance.order_date),
            'items':          items,
        }

    else:
        # Generic fallback
        from django.core import serializers as dj_s
        return json.loads(dj_s.serialize('json', [instance]))[0]


def queue_for_sync(instance, operation='create'):
    """
    Add a model instance to the sync queue.
    De-duplicates: if a pending entry for the same object exists, updates it.
    Never raises - sync failure must never block the main operation.
    """
    try:
        payload = build_payload(instance)
        payload['_operation'] = operation
        payload['_local_id']  = instance.pk

        ct = ContentType.objects.get_for_model(instance)

        existing = SyncQueue.objects.filter(
            content_type=ct,
            object_id=instance.pk,
            status='pending'
        ).first()

        if existing:
            existing.payload   = payload
            existing.operation = operation
            existing.save(update_fields=['payload', 'operation'])
        else:
            SyncQueue.objects.create(
                content_type=ct,
                object_id=instance.pk,
                operation=operation,
                payload=payload,
            )

        # Fire-and-forget background sync if cloud is configured
        _background_sync()

    except Exception:
        pass  # Never block the caller


def _background_sync():
    """
    Attempt a sync in a background thread so the caller is not blocked.
    Only runs if CLOUD_SYNC_URL is configured and there are pending items.
    """
    def _run():
        try:
            from django.conf import settings as s
            if not getattr(s, 'CLOUD_SYNC_URL', ''):
                return
            # Import here to avoid circular imports
            from sync_engine.views import _do_sync
            _do_sync()
        except Exception:
            pass

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()