from django.db import models
from django.contrib.auth.models import User
from shops.models import Shop
from products.models import Product, ProductVariant


class Supplier(models.Model):
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class PurchaseOrder(models.Model):
    STATUS_CHOICES = [
        ('draft',     'Draft'),
        ('confirmed', 'Confirmed - Sent to Supplier'),
        ('in_transit','In Transit'),
        ('arrived',   'Arrived - Pending Inspection'),
        ('partial',   'Partially Received'),
        ('received',  'Fully Received'),
        ('cancelled', 'Cancelled'),
    ]

    order_number  = models.CharField(max_length=20, unique=True, blank=True)
    shop          = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='purchase_orders')
    supplier      = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='orders')
    status        = models.CharField(max_length=15, choices=STATUS_CHOICES, default='draft')
    order_date    = models.DateField(auto_now_add=True)
    expected_date = models.DateField(null=True, blank=True)
    arrived_date  = models.DateField(null=True, blank=True)
    received_date = models.DateField(null=True, blank=True)
    notes         = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)

    # Financials (auto-calculated)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total    = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_orders')
    confirmed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='confirmed_orders')
    received_by  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='received_orders')
    synced = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.order_number} - {self.supplier.name}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            count = PurchaseOrder.objects.count() + 1
            self.order_number = f"PO-{count:04d}"
        super().save(*args, **kwargs)

    def recalculate_totals(self):
        from django.db.models import Sum
        self.subtotal = self.items.aggregate(t=Sum('line_total'))['t'] or 0
        self.total = self.subtotal
        self.save(update_fields=['subtotal', 'total'])

    @property
    def items_count(self):
        return self.items.count()

    @property
    def is_editable(self):
        return self.status == 'draft'

    @property
    def can_confirm(self):
        return self.status == 'draft' and self.items.exists()

    @property
    def can_mark_arrived(self):
        return self.status in ('confirmed', 'in_transit')

    @property
    def can_receive(self):
        return self.status in ('arrived', 'partial')

    @property
    def receive_progress(self):
        items = list(self.items.all())
        if not items:
            return 0
        total_ordered = sum(i.quantity_ordered for i in items)
        total_received = sum(i.quantity_received for i in items)
        if total_ordered == 0:
            return 0
        return int((total_received / total_ordered) * 100)


class PurchaseOrderItem(models.Model):
    order            = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    product          = models.ForeignKey(Product, on_delete=models.CASCADE)
    variant          = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True)
    quantity_ordered  = models.IntegerField()
    quantity_received = models.IntegerField(default=0)
    quantity_rejected = models.IntegerField(default=0)   # failed inspection
    unit_cost        = models.DecimalField(max_digits=12, decimal_places=2)
    line_total       = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    inspection_notes = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        self.line_total = self.unit_cost * self.quantity_ordered
        super().save(*args, **kwargs)

    def __str__(self):
        v = f" ({self.variant})" if self.variant else ""
        return f"{self.product.name}{v} x{self.quantity_ordered}"

    @property
    def quantity_pending(self):
        """Units not yet accounted for - neither accepted nor rejected."""
        return max(0, self.quantity_ordered - self.quantity_received - self.quantity_rejected)

    @property
    def is_fully_received(self):
        """True when all units are either accepted or rejected - nothing left pending."""
        return self.quantity_pending == 0
