from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from shops.models import Shop, DaySession
from products.models import Product, ProductVariant
from customers.models import Customer


class Motorcycle(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('maintenance', 'Maintenance'),
    ]

    plate_number = models.CharField(max_length=20)
    make = models.CharField(max_length=50, blank=True)
    model = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=30, blank=True)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='motorcycles')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='active')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['plate_number']

    def __str__(self):
        return f"{self.plate_number} ({self.make} {self.model})".strip()


class Driver(models.Model):
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='drivers')
    motorcycle = models.ForeignKey(
        Motorcycle, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='drivers'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def active_orders_count(self):
        return self.delivery_orders.exclude(status__in=['closed', 'cancelled']).count()


class DeliveryOrder(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('picked_up', 'Picked Up'),
        ('delivered', 'Delivered'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ]

    order_number = models.CharField(max_length=20, unique=True, blank=True)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='delivery_orders')
    day_session = models.ForeignKey(
        DaySession, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='delivery_orders'
    )
    driver = models.ForeignKey(Driver, on_delete=models.PROTECT, related_name='delivery_orders')

    # Financials
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    delivery_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')

    # Set when order is closed
    sale = models.OneToOneField(
        'pos.Sale', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='delivery_order'
    )
    closed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='closed_delivery_orders'
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='created_delivery_orders'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Delivery {self.order_number}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            today = timezone.now().strftime('%Y%m%d')
            count = DeliveryOrder.objects.filter(
                shop=self.shop,
                created_at__date=timezone.now().date()
            ).count() + 1
            self.order_number = f"DEL-{today}-{count:04d}"
        super().save(*args, **kwargs)

    @property
    def is_open(self):
        return self.status not in ('closed', 'cancelled')

    @property
    def stops_count(self):
        return self.stops.count()

    @property
    def all_items(self):
        """Flat list of all items across all stops."""
        from itertools import chain
        return list(chain.from_iterable(s.items.select_related('product', 'variant') for s in self.stops.all()))


class DeliveryStop(models.Model):
    """One customer destination within a delivery order."""

    order = models.ForeignKey(DeliveryOrder, on_delete=models.CASCADE, related_name='stops')
    sequence = models.PositiveIntegerField(default=1)
    customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='delivery_stops'
    )
    customer_name = models.CharField(max_length=100, blank=True)
    customer_phone = models.CharField(max_length=20, blank=True)
    delivery_address = models.TextField(blank=True)
    delivery_notes = models.TextField(blank=True)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ['sequence']

    def __str__(self):
        return f"Stop {self.sequence} – {self.display_customer_name}"

    @property
    def display_customer_name(self):
        if self.customer:
            return self.customer.name
        return self.customer_name or f'Stop {self.sequence}'

    @property
    def display_customer_phone(self):
        if self.customer:
            return self.customer.phone
        return self.customer_phone or '—'


class DeliveryStopItem(models.Model):
    stop = models.ForeignKey(DeliveryStop, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    buying_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)

    def save(self, *args, **kwargs):
        self.line_total = self.unit_price * self.quantity
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"

    @property
    def profit(self):
        return (self.unit_price - self.buying_price) * self.quantity
