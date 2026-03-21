from django import forms
from .models import Product, Category


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'name', 'category', 'uom', 'description', 'image',
            'selling_price', 'buying_price', 'tax_inclusive',
            'track_stock', 'low_stock_threshold', 'is_active',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, shop=None, **kwargs):
        super().__init__(*args, **kwargs)
        if shop:
            self.fields['category'].queryset = Category.objects.filter(shop=shop, is_active=True)


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description']


class VariantForm(forms.Form):
    variant_type = forms.CharField(max_length=50, label='Variant Type (e.g. Color, Size)')
    value = forms.CharField(max_length=100, label='Value (e.g. Black, Large)')
