from django.db import models
from shops.models import Shop


class Customer(models.Model):
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='customers', null=True, blank=True)
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credit_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)  # amount owed
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def has_debt(self):
        return self.credit_balance > 0


class CreditPayment(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='credit_payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=10, choices=[('cash', 'Cash'), ('mpesa', 'M-Pesa')])
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.customer.name} - TSh {self.amount}"
