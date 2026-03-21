from django.db import models
from shops.models import Shop


class ShopSettings(models.Model):
    """Per-shop configurable settings stored in the database."""
    shop = models.OneToOneField(Shop, on_delete=models.CASCADE, related_name='settings')

    # General
    currency = models.CharField(max_length=10, default='TSh')
    language = models.CharField(max_length=5, default='sw', choices=[('sw', 'Kiswahili'), ('en', 'English')])
    timezone = models.CharField(max_length=50, default='Africa/Dar_es_Salaam')

    # Tax
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=18.00)
    tax_name = models.CharField(max_length=20, default='VAT')
    tax_inclusive = models.BooleanField(default=True)

    # Stock
    low_stock_threshold = models.IntegerField(default=10)
    auto_reorder = models.BooleanField(default=False)

    # POS
    require_customer_on_credit = models.BooleanField(default=True)
    allow_negative_stock = models.BooleanField(default=False)
    print_receipt_auto = models.BooleanField(default=False)

    # Daily report
    daily_report_enabled = models.BooleanField(default=True)
    daily_report_time = models.TimeField(default='22:00')
    daily_report_email = models.EmailField(blank=True)
    daily_report_whatsapp = models.CharField(max_length=20, blank=True)

    # Receipt
    receipt_header = models.TextField(blank=True, help_text='Text shown at top of receipt')
    receipt_footer = models.TextField(blank=True, default='Thank you for shopping with us!')
    show_tax_on_receipt = models.BooleanField(default=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'shop settings'

    def __str__(self):
        return f"Settings - {self.shop.name}"
