from django import forms
from .models import UnitOfMeasure

class UOMForm(forms.ModelForm):
    class Meta:
        model = UnitOfMeasure
        fields = ['name', 'short_name', 'allow_decimals', 'is_active', 'sort_order']
