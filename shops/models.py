from django.db import models
from django.contrib.auth.models import User


class Shop(models.Model):
    SHOP_TYPE_CHOICES = [
        ('handbags', 'Handbags'),
        ('hair', 'Hair Products'),
        ('home', 'Home Supplies'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=100)
    shop_type = models.CharField(max_length=20, choices=SHOP_TYPE_CHOICES)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class UserShopAccess(models.Model):
    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('admin', 'Admin'),
        ('cashier', 'Cashier'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shop_access')
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='user_access')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='cashier')
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('user', 'shop')

    def __str__(self):
        return f"{self.user.username} @ {self.shop.name} ({self.role})"


class DaySession(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('closed', 'Closed'),
    ]

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='day_sessions')
    opened_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='opened_sessions')
    closed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='closed_sessions')
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='open')
    opening_cash = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    closing_cash = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    report_sent = models.BooleanField(default=False)

    # Daily totals (calculated on close)
    total_sales = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_cash = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_mpesa = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_credit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_transactions = models.IntegerField(default=0)
    gross_profit = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        unique_together = ('shop', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"{self.shop.name} - {self.date} ({self.status})"

    @property
    def is_open(self):
        return self.status == 'open'
