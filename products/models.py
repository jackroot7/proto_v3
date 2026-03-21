from django.db import models
from shops.models import Shop


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='categories', null=True, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class VariantType(models.Model):
    """e.g. Color, Size, Volume"""
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=50, unique=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='products')
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='products/', null=True, blank=True)

    # Pricing
    selling_price = models.DecimalField(max_digits=12, decimal_places=2)
    buying_price  = models.DecimalField(max_digits=12, decimal_places=2)
    tax_inclusive = models.BooleanField(default=True)

    # Unit of Measure
    uom = models.ForeignKey(
        'units.UnitOfMeasure',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='products',
        verbose_name='Unit of Measure',
        help_text='e.g. Piece, Kg, Litre, Packet'
    )

    # Stock
    track_stock = models.BooleanField(default=True)
    low_stock_threshold = models.IntegerField(default=10)

    is_active = models.BooleanField(default=True)
    has_variants = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.shop.name})"

    def save(self, *args, **kwargs):
        if not self.sku:
            prefix = self.category.slug[:3].upper() if self.category else 'PRD'
            import uuid
            self.sku = f"{prefix}-{str(uuid.uuid4())[:6].upper()}"
        super().save(*args, **kwargs)

    @property
    def profit_margin(self):
        if self.buying_price > 0:
            return ((self.selling_price - self.buying_price) / self.selling_price) * 100
        return 0

    @property
    def current_stock(self):
        from stock.models import StockLevel
        try:
            return StockLevel.objects.get(product=self, shop=self.shop).quantity
        except:
            return 0


class ProductVariantType(models.Model):
    """Links a VariantType to a Product (e.g. Gucci Bag has Color + Size)"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variant_types')
    variant_type = models.ForeignKey(VariantType, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('product', 'variant_type')

    def __str__(self):
        return f"{self.product.name} - {self.variant_type.name}"


class ProductVariant(models.Model):
    """A specific variant of a product (e.g. Gucci Bag, Black, Medium)"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    sku = models.CharField(max_length=80, unique=True, blank=True)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    buying_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        attrs = ', '.join([f"{a.variant_type.name}: {a.value}" for a in self.attributes.all()])
        return f"{self.product.name} ({attrs})"

    def save(self, *args, **kwargs):
        if not self.sku:
            import uuid
            self.sku = f"{self.product.sku}-{str(uuid.uuid4())[:4].upper()}"
        super().save(*args, **kwargs)

    @property
    def effective_selling_price(self):
        return self.selling_price if self.selling_price else self.product.selling_price

    @property
    def effective_buying_price(self):
        return self.buying_price if self.buying_price else self.product.buying_price


class VariantAttribute(models.Model):
    """e.g. variant=Gucci Bag v1, variant_type=Color, value=Black"""
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name='attributes')
    variant_type = models.ForeignKey(VariantType, on_delete=models.CASCADE)
    value = models.CharField(max_length=100)

    class Meta:
        unique_together = ('variant', 'variant_type')

    def __str__(self):
        return f"{self.variant_type.name}: {self.value}"
