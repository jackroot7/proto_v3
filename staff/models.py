from django.db import models
from django.contrib.auth.models import User
from shops.models import Shop


class StaffProfile(models.Model):
    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('admin', 'Admin / Manager'),
        ('cashier', 'Cashier'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('on_leave', 'On Leave'),
        ('terminated', 'Terminated'),
        ('suspended', 'Suspended'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='staff_profile')
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='staff')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    phone = models.CharField(max_length=20, blank=True)
    national_id = models.CharField(max_length=30, blank=True)
    hire_date = models.DateField()
    monthly_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='active')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.role})"


class AttendanceRecord(models.Model):
    staff = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name='attendance')
    date = models.DateField()
    time_in = models.TimeField(null=True, blank=True)
    time_out = models.TimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ('staff', 'date')


class DisciplinaryRecord(models.Model):
    SEVERITY_CHOICES = [
        ('warning', 'Verbal Warning'),
        ('written', 'Written Warning'),
        ('suspension', 'Suspension'),
        ('termination', 'Termination'),
    ]

    staff = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name='disciplinary_records')
    severity = models.CharField(max_length=15, choices=SEVERITY_CHOICES)
    incident_date = models.DateField()
    description = models.TextField()
    action_taken = models.TextField(blank=True)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.staff} - {self.severity} ({self.incident_date})"
