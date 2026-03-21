from django.conf import settings as django_settings
from .models import ShopSettings


def get_shop_settings(shop):
    """Return ShopSettings for a shop, creating defaults if needed."""
    obj, _ = ShopSettings.objects.get_or_create(
        shop=shop,
        defaults={
            'tax_rate': getattr(django_settings, 'PROTO_TAX_RATE', 18) * 100,
            'low_stock_threshold': getattr(django_settings, 'PROTO_LOW_STOCK_THRESHOLD', 10),
        }
    )
    return obj


def get_tax_rate(shop):
    """Return decimal tax rate (e.g. 0.18) for a shop."""
    from decimal import Decimal
    try:
        s = ShopSettings.objects.get(shop=shop)
        return s.tax_rate / 100
    except ShopSettings.DoesNotExist:
        return Decimal('0.18')


def get_low_stock_threshold(shop):
    try:
        return ShopSettings.objects.get(shop=shop).low_stock_threshold
    except ShopSettings.DoesNotExist:
        return 10
