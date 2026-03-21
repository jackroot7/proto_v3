from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import SyncQueue, SyncLog
import time


@login_required
def sync_status(request):
    pending = SyncQueue.objects.filter(status='pending').count()
    last_log = SyncLog.objects.order_by('-created_at').first()
    return JsonResponse({
        'pending': pending,
        'last_sync': last_log.created_at.isoformat() if last_log else None,
        'online': True,
    })


@login_required
@require_POST
def trigger_sync(request):
    """Trigger a manual sync attempt."""
    start = time.time()
    pending = SyncQueue.objects.filter(status='pending')
    synced = 0
    failed = 0
    for item in pending:
        try:
            # In production: POST to cloud server here
            # response = requests.post(CLOUD_URL, json=item.payload)
            item.status = 'synced'
            item.synced_at = timezone.now()
            item.save()
            synced += 1
        except Exception as e:
            item.status = 'failed'
            item.attempts += 1
            item.error_message = str(e)
            item.save()
            failed += 1

    duration = time.time() - start
    SyncLog.objects.create(
        direction='up', records_synced=synced,
        records_failed=failed, duration_seconds=duration,
    )
    return JsonResponse({'synced': synced, 'failed': failed, 'duration': round(duration, 2)})
