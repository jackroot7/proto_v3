from django import forms
from .models import ShopSettings


class ShopSettingsForm(forms.ModelForm):
    class Meta:
        model = ShopSettings
        exclude = ['shop', 'updated_at']
        widgets = {
            'daily_report_time': forms.TimeInput(attrs={'type': 'time'}),
            'receipt_header': forms.Textarea(attrs={'rows': 2}),
            'receipt_footer': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make time field optional - don't block saves
        self.fields['daily_report_time'].required = False
        self.fields['daily_report_email'].required = False
        self.fields['daily_report_whatsapp'].required = False
        self.fields['receipt_header'].required = False
        self.fields['receipt_footer'].required = False

        # Better labels
        self.fields['tax_rate'].label = 'Tax rate (%)'
        self.fields['low_stock_threshold'].label = 'Low stock alert threshold (units)'
        self.fields['daily_report_time'].label = 'Scheduled send time'
        self.fields['daily_report_email'].label = 'Owner email'
        self.fields['daily_report_whatsapp'].label = 'Owner WhatsApp number'
        self.fields['allow_negative_stock'].label = 'Allow sales when stock reaches zero'
        self.fields['require_customer_on_credit'].label = 'Require customer name for credit sales'
        self.fields['print_receipt_auto'].label = 'Auto-open print dialog after each sale'
        self.fields['show_tax_on_receipt'].label = 'Show tax breakdown on receipt'
        self.fields['auto_reorder'].label = 'Show reorder suggestions on dashboard'
        self.fields['daily_report_enabled'].label = 'Send daily report on day close'
        self.fields['tax_inclusive'].label = 'Prices include tax (tax-inclusive)'
