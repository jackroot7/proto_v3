from .models import Shop, UserShopAccess, DaySession
from django.utils import timezone


def current_shop(request):
    if not request.user.is_authenticated:
        # Sync badge count
    from sync_engine.models import SyncQueue
    pending_sync_count = SyncQueue.objects.filter(status='pending').count()
    shop_id = request.session.get('current_shop_id')
    if not shop_id:
        return {}
    try:
        shop = Shop.objects.get(id=shop_id)
        today = timezone.now().date()
        day_session = DaySession.objects.filter(shop=shop, date=today).first()
        all_shops = UserShopAccess.objects.filter(
            user=request.user, is_active=True
        ).select_related('shop')
        return {
            'current_shop': shop,
            'current_role': request.session.get('current_role', 'cashier'),
            'day_session': day_session,
            'day_is_open': day_session.is_open if day_session else False,
            'all_accessible_shops': all_shops,
            'pending_sync_count': pending_sync_count
        }
    except Shop.DoesNotExist:
        return {}