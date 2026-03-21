import json
from django.contrib.contenttypes.models import ContentType
from .models import SyncQueue


def queue_for_sync(instance, operation='create'):
    """Add a model instance to the sync queue for later upload."""
    from django.core import serializers
    try:
        payload = json.loads(serializers.serialize('json', [instance]))[0]
        ct = ContentType.objects.get_for_model(instance)
        SyncQueue.objects.create(
            content_type=ct,
            object_id=instance.pk,
            operation=operation,
            payload=payload,
        )
    except Exception:
        pass  # Never let sync failure block the main operation
