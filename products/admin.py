from django.contrib import admin
from .models import Category, Product, ProductVariant, VariantType, VariantAttribute, ProductVariantType
admin.site.register(Category)
admin.site.register(Product)
admin.site.register(ProductVariant)
admin.site.register(VariantType)
admin.site.register(VariantAttribute)
admin.site.register(ProductVariantType)