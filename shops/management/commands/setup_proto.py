"""
Management command: python manage.py setup_proto
Creates the initial shops, owner user, categories, and expense categories.
Run this once after first migration.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from shops.models import Shop, UserShopAccess
from products.models import Category
from expenses.models import ExpenseCategory
import random, string


class Command(BaseCommand):
    help = 'Set up initial Proto v3 data: shops, owner, categories'

    def add_arguments(self, parser):
        parser.add_argument('--owner-username', default='owner')
        parser.add_argument('--owner-password', default='proto2024')
        parser.add_argument('--owner-name', default='Shop Owner')

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('\n=== Proto v3 Initial Setup ===\n'))

        # Create 3 shops
        shops_data = [
            {'name': 'Handbags Shop', 'shop_type': 'handbags'},
            {'name': 'Hair Products Shop', 'shop_type': 'hair'},
            {'name': 'Home Supplies Shop', 'shop_type': 'home'},
        ]
        shops = []
        for sd in shops_data:
            shop, created = Shop.objects.get_or_create(name=sd['name'], defaults=sd)
            shops.append(shop)
            if created:
                self.stdout.write(f'  Created shop: {shop.name}')
            else:
                self.stdout.write(f'  Shop exists: {shop.name}')

        # Create owner user
        username = options['owner_username']
        password = options['owner_password']
        name_parts = options['owner_name'].split(' ', 1)
        first = name_parts[0]
        last = name_parts[1] if len(name_parts) > 1 else ''

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'first_name': first, 'last_name': last,
                'is_staff': True, 'is_superuser': True,
            }
        )
        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(f'  Created owner: {username} / {password}')
        else:
            self.stdout.write(f'  Owner exists: {username}')

        # Give owner access to all shops
        for shop in shops:
            access, created = UserShopAccess.objects.get_or_create(
                user=user, shop=shop,
                defaults={'role': 'owner'}
            )
            if created:
                self.stdout.write(f'  Access granted: {username} → {shop.name}')

        # Create product categories per shop
        categories_map = {
            'Handbags Shop': ['Bags', 'Wallets', 'Accessories', 'Belts'],
            'Hair Products Shop': ['Hair Care', 'Shampoo', 'Oils & Serums', 'Tools'],
            'Home Supplies Shop': ['Home Decor', 'Bedding', 'Kitchen', 'Cleaning'],
        }
        from django.utils.text import slugify
        for shop in shops:
            for cat_name in categories_map.get(shop.name, []):
                slug = slugify(cat_name)
                base_slug = slug
                n = 1
                while Category.objects.filter(slug=slug).exists():
                    slug = f"{base_slug}-{n}"
                    n += 1
                cat, created = Category.objects.get_or_create(
                    name=cat_name, shop=shop,
                    defaults={'slug': slug}
                )
                if created:
                    self.stdout.write(f'  Category: {cat_name} → {shop.name}')

        # Create expense categories
        expense_cats = [
            'Shop Rent', 'Staff Salaries', 'Electricity / Water',
            'Marketing & Advertising', 'Transport', 'Supplies',
            'Repairs & Maintenance', 'Tax & Licenses', 'Other',
        ]
        for name in expense_cats:
            ec, created = ExpenseCategory.objects.get_or_create(name=name)
            if created:
                self.stdout.write(f'  Expense category: {name}')

        # Create default Units of Measure
        from units.models import UnitOfMeasure
        default_uoms = [
            ('Piece',   'pcs',  False, 1),
            ('Kilogram','kg',   True,  2),
            ('Gram',    'g',    True,  3),
            ('Litre',   'ltr',  True,  4),
            ('Millilitre','ml', True,  5),
            ('Packet',  'pkt',  False, 6),
            ('Box',     'box',  False, 7),
            ('Dozen',   'doz',  False, 8),
            ('Pair',    'pair', False, 9),
            ('Metre',   'm',    True,  10),
            ('Roll',    'roll', False, 11),
            ('Bottle',  'btl',  False, 12),
            ('Bag',     'bag',  False, 13),
            ('Carton',  'ctn',  False, 14),
            ('Set',     'set',  False, 15),
        ]
        for name, short, decimals, order in default_uoms:
            uom, created = UnitOfMeasure.objects.get_or_create(
                name=name,
                defaults={'short_name': short, 'allow_decimals': decimals, 'sort_order': order}
            )
            if created:
                self.stdout.write(f'  UOM: {name} ({short})')

        self.stdout.write(self.style.SUCCESS('\n✓ Proto v3 setup complete!\n'))
        self.stdout.write(f'  Login URL : http://localhost:8000/login/')
        self.stdout.write(f'  Username  : {username}')
        self.stdout.write(f'  Password  : {password}')
        self.stdout.write(f'  Admin URL : http://localhost:8000/admin/\n')
