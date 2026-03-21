from django.db import models
from django.contrib.auth.models import User
from shops.models import Shop
from products.models import Product, ProductVariant


class StockLevel(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_levels')
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, null=True, blank=True, related_name='stock_levels')
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='stock_levels')
    quantity = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('product', 'variant', 'shop')

    def __str__(self):
        v = f" - {self.variant}" if self.variant else ""
        return f"{self.product.name}{v} @ {self.shop.name}: {self.quantity}"

    @property
    def is_low(self):
        threshold = self.product.low_stock_threshold
        return self.quantity <= threshold

    @property
    def is_critical(self):
        return self.quantity <= 3


class StockMovement(models.Model):
    MOVEMENT_TYPES = [
        ('sale', 'Sale'),
        ('purchase', 'Purchase / Restock'),
        ('adjustment', 'Manual Adjustment'),
        ('return', 'Customer Return'),
        ('transfer', 'Shop Transfer'),
        ('damage', 'Damage / Loss'),
        ('opening', 'Opening Stock'),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='movements')
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, null=True, blank=True)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='stock_movements')
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES)
    quantity = models.IntegerField()  # positive = in, negative = out
    quantity_before = models.IntegerField(default=0)
    quantity_after = models.IntegerField(default=0)
    reference = models.CharField(max_length=100, blank=True)  # PO number, sale number etc
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.movement_type}: {self.product.name} x{self.quantity} @ {self.shop.name}"


class StockTake(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    ]

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE)
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    conducted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Stock Take - {self.shop.name} {self.date}"


class StockTakeItem(models.Model):
    stock_take = models.ForeignKey(StockTake, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, null=True, blank=True)
    system_quantity = models.IntegerField()
    counted_quantity = models.IntegerField(null=True, blank=True)
    discrepancy = models.IntegerField(default=0)

    def save(self, *args, **kwargs):
        if self.counted_quantity is not None:
            self.discrepancy = self.counted_quantity - self.system_quantity
        super().save(*args, **kwargs)
