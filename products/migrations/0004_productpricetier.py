from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0003_optional_base_price'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductPriceTier',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('min_quantity', models.PositiveIntegerField()),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=12)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='price_tiers', to='products.product')),
                ('variant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='price_tiers', to='products.productvariant')),
            ],
            options={
                'ordering': ['-min_quantity'],
                'unique_together': {('product', 'variant', 'min_quantity')},
            },
        ),
    ]
