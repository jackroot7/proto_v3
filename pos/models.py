from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from shops.models import Shop, DaySession
from products.models import Product, ProductVariant
from customers.models import Customer


class Sale(models.Model):
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('mpesa', 'M-Pesa'),
        ('credit', 'Credit / Borrow'),
        ('split', 'Split Payment'),
    ]

    STATUS_CHOICES = [
        ('completed', 'Completed'),
        ('voided', 'Voided'),
        ('refunded', 'Refunded'),
    ]

    sale_number = models.CharField(max_length=20, unique=True, blank=True)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='sales')
    day_session = models.ForeignKey(DaySession, on_delete=models.SET_NULL, null=True, blank=True, related_name='sales')
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='sales')
    cashier = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='sales')

    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHODS)
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    change_given = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='completed')
    voided_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='voided_sales')
    void_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    synced = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Sale {self.sale_number} - {self.shop.name}"

    def save(self, *args, **kwargs):
        if not self.sale_number:
            today = timezone.now().strftime('%Y%m%d')
            count = Sale.objects.filter(shop=self.shop, created_at__date=timezone.now().date()).count() + 1
            self.sale_number = f"SA-{today}-{count:04d}"
        super().save(*args, **kwargs)


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    buying_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)

    def save(self, *args, **kwargs):
        self.line_total = (self.unit_price * self.quantity) - self.discount
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"

    @property
    def profit(self):
        return (self.unit_price - self.buying_price) * self.quantity
