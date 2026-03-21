from django import forms
from .models import Customer, CreditPayment


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'phone', 'email', 'address', 'credit_limit', 'notes']
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}


class CreditPaymentForm(forms.ModelForm):
    class Meta:
        model = CreditPayment
        fields = ['amount', 'payment_method', 'reference', 'notes']
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, max_amount=None, **kwargs):
        super().__init__(*args, **kwargs)
        if max_amount is not None:
            self.fields['amount'].max_value = max_amount
            self.fields['amount'].widget.attrs['max'] = str(max_amount)
            self.fields['amount'].widget.attrs['placeholder'] = f'Max: TSh {max_amount:,.0f}'
            self.fields['amount'].help_text = f'Maximum payable: TSh {max_amount:,.0f}'
