from .models import ShopSettings


def shop_settings(request):
    """Inject current shop's settings into every template context."""
    shop_id = request.session.get('current_shop_id')
    if not shop_id or not request.user.is_authenticated:
        return {'shop_settings': None}
    try:
        settings_obj = ShopSettings.objects.get(shop_id=shop_id)
    except ShopSettings.DoesNotExist:
        settings_obj = None
    return {'shop_settings': settings_obj}
