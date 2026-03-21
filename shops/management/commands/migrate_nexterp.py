"""
Management command: migrate_nexterp
Imports products from a NextERP Item.csv export into Proto v3.

Usage:
    python manage.py migrate_nexterp --file /path/to/Item.csv --shop <shop_id>
    python manage.py migrate_nexterp --file /path/to/Item.csv --shop 1 --selling-price 5000 --buying-price 3000

Options:
    --file          Path to the NextERP Item.csv file (required)
    --shop          Shop ID to import into (required)
    --selling-price Default selling price for all products (default: 0 - edit after import)
    --buying-price  Default buying price for all products (default: 0)
    --dry-run       Preview what will be imported without saving anything
"""

import csv
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify


class Command(BaseCommand):
    help = 'Migrate products from NextERP Item.csv export into Proto v3'

    def add_arguments(self, parser):
        parser.add_argument('--file',          required=True,  help='Path to Item.csv')
        parser.add_argument('--shop',          required=True,  type=int, help='Shop ID')
        parser.add_argument('--selling-price', type=float, default=0, help='Default selling price')
        parser.add_argument('--buying-price',  type=float, default=0, help='Default buying price')
        parser.add_argument('--dry-run',       action='store_true', help='Preview only, no DB writes')

    def handle(self, *args, **options):
        from shops.models import Shop
        from products.models import Product, Category, ProductVariant, VariantType, VariantAttribute, ProductVariantType
        from units.models import UnitOfMeasure
        from decimal import Decimal

        dry_run       = options['dry_run']
        selling_price = Decimal(str(options['selling_price']))
        buying_price  = Decimal(str(options['buying_price']))

        # ── Load shop ──────────────────────────────────────────
        try:
            shop = Shop.objects.get(pk=options['shop'])
        except Shop.DoesNotExist:
            raise CommandError(f"Shop with ID {options['shop']} not found.")

        self.stdout.write(f"\nMigrating into: {shop.name} (ID {shop.id})")
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - nothing will be saved\n'))

        # ── Read CSV ───────────────────────────────────────────
        try:
            with open(options['file'], encoding='utf-8-sig') as f:
                rows = list(csv.DictReader(f))
        except FileNotFoundError:
            raise CommandError(f"File not found: {options['file']}")

        self.stdout.write(f"CSV rows: {len(rows)}\n")

        # ── Resolve or create UOM ──────────────────────────────
        uom_map = {}
        for uom_name in set(r['Default Unit of Measure'].strip() for r in rows):
            if not uom_name:
                continue
            # Map NextERP names to Proto v3 UOM names
            mapped = {
                'Nos': 'Piece', 'nos': 'Piece',
                'Unit': 'Piece', 'unit': 'Piece',
                'Kg': 'Kilogram', 'kg': 'Kilogram',
                'Ltr': 'Litre', 'ltr': 'Litre',
            }.get(uom_name, uom_name)

            uom = UnitOfMeasure.objects.filter(name__iexact=mapped).first()
            if not uom:
                uom = UnitOfMeasure.objects.filter(short_name__iexact=uom_name).first()
            if not uom and not dry_run:
                uom = UnitOfMeasure.objects.create(
                    name=mapped, short_name=uom_name.lower(), allow_decimals=False, sort_order=99
                )
                self.stdout.write(f'  Created UOM: {mapped}')
            uom_map[uom_name] = uom

        # ── Resolve or create Category ─────────────────────────
        cat_map = {}
        for group in set(r['Item Group'].strip() for r in rows if r['Item Group'].strip()):
            cat = Category.objects.filter(name__iexact=group, shop=shop).first()
            if not cat and not dry_run:
                slug = slugify(group)
                base_slug = slug
                n = 1
                while Category.objects.filter(slug=slug).exists():
                    slug = f"{base_slug}-{n}"; n += 1
                cat = Category.objects.create(name=group, slug=slug, shop=shop)
                self.stdout.write(f'  Created category: {group}')
            cat_map[group] = cat

        # ── Identify parents and variants ──────────────────────
        # parent = rows where Variant Of is empty (or the parent name itself)
        # variant = rows where Variant Of is set

        # Find all unique parent names
        parent_names = set()
        for r in rows:
            variant_of = r['Variant Of'].strip()
            if variant_of:
                parent_names.add(variant_of)
            else:
                # Could be a standalone product with no variants
                if not any(r2['Variant Of'].strip() == r['Item Name'].strip() for r2 in rows):
                    parent_names.add(r['Item Name'].strip())

        # Build parent → variants map
        parent_to_variants = {p: [] for p in parent_names}
        for r in rows:
            variant_of = r['Variant Of'].strip()
            if variant_of and variant_of in parent_to_variants:
                parent_to_variants[variant_of].append(r)

        # Also collect standalone rows (no variants at all)
        standalone_names = set()
        for r in rows:
            variant_of = r['Variant Of'].strip()
            name = r['Item Name'].strip()
            if not variant_of and name not in parent_names:
                standalone_names.add(name)

        # ── Get or create Colour VariantType ───────────────────
        colour_type = None
        if not dry_run:
            colour_type, _ = VariantType.objects.get_or_create(name='Colour')

        # ── Import ─────────────────────────────────────────────
        created_products  = 0
        updated_products  = 0
        created_variants  = 0
        skipped           = 0
        errors            = []

        for parent_name, variant_rows in parent_to_variants.items():
            # Find the group/UOM from the first variant row (or standalone)
            sample = variant_rows[0] if variant_rows else next(
                (r for r in rows if r['Item Name'].strip() == parent_name), None
            )
            if not sample:
                errors.append(f'No data found for parent: {parent_name}')
                continue

            group   = sample['Item Group'].strip()
            uom_key = sample['Default Unit of Measure'].strip()
            uom     = uom_map.get(uom_key)
            cat     = cat_map.get(group)

            has_variants = len(variant_rows) > 0

            if dry_run:
                action = '(new)' if not Product.objects.filter(
                    name__iexact=parent_name, shop=shop).exists() else '(exists)'
                self.stdout.write(
                    f'  Product: {parent_name} {action} | '
                    f'Category: {group} | '
                    f'UOM: {uom_key} | '
                    f'{len(variant_rows)} variant(s)'
                )
                for vr in variant_rows:
                    colour = self._extract_colour(vr['Item Name'], parent_name)
                    self.stdout.write(f'         Variant → Colour: {colour}')
                created_products += 1
                created_variants += len(variant_rows)
                continue

            # Create or update parent product
            product, created = Product.objects.get_or_create(
                name__iexact=parent_name,
                shop=shop,
                defaults={
                    'name': parent_name,
                    'shop': shop,
                    'category': cat,
                    'uom': uom,
                    'selling_price': selling_price,
                    'buying_price': buying_price,
                    'has_variants': has_variants,
                    'track_stock': True,
                    'is_active': True,
                }
            )

            if not created:
                # Update category and UOM if missing
                save_fields = []
                if not product.category and cat:
                    product.category = cat; save_fields.append('category')
                if not product.uom and uom:
                    product.uom = uom; save_fields.append('uom')
                if has_variants and not product.has_variants:
                    product.has_variants = True; save_fields.append('has_variants')
                if save_fields:
                    product.save(update_fields=save_fields)
                updated_products += 1
            else:
                created_products += 1

            # Link VariantType to product
            if has_variants and colour_type:
                ProductVariantType.objects.get_or_create(product=product, variant_type=colour_type)

            # Create variants
            for vr in variant_rows:
                colour = self._extract_colour(vr['Item Name'], parent_name)

                # Check if this colour variant already exists
                existing = VariantAttribute.objects.filter(
                    variant__product=product,
                    variant_type=colour_type,
                    value__iexact=colour
                ).first()

                if existing:
                    skipped += 1
                    continue

                variant = ProductVariant.objects.create(
                    product=product,
                    is_active=True,
                )
                VariantAttribute.objects.create(
                    variant=variant,
                    variant_type=colour_type,
                    value=colour,
                )
                created_variants += 1

        # ── Standalone products (no variants) ─────────────────
        for r in rows:
            name      = r['Item Name'].strip()
            group     = r['Item Group'].strip()
            uom_key   = r['Default Unit of Measure'].strip()
            variant_of = r['Variant Of'].strip()

            # Only process if not a variant and not already handled as parent
            if variant_of or name in parent_names:
                continue

            cat = cat_map.get(group)
            uom = uom_map.get(uom_key)

            if dry_run:
                self.stdout.write(f'  Standalone: {name} | {group} | {uom_key}')
                created_products += 1
                continue

            _, created = Product.objects.get_or_create(
                name__iexact=name, shop=shop,
                defaults={
                    'name': name, 'shop': shop, 'category': cat, 'uom': uom,
                    'selling_price': selling_price, 'buying_price': buying_price,
                    'has_variants': False, 'track_stock': True, 'is_active': True,
                }
            )
            if created:
                created_products += 1
            else:
                updated_products += 1

        # ── Summary ────────────────────────────────────────────
        self.stdout.write('')
        if errors:
            self.stdout.write(self.style.ERROR(f'Errors ({len(errors)}):'))
            for e in errors:
                self.stdout.write(f'  ✕ {e}')
            self.stdout.write('')

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'DRY RUN complete - would create ~{created_products} products '
                f'with ~{created_variants} variants.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'\n✓ Migration complete!\n'
                f'  Products created : {created_products}\n'
                f'  Products updated : {updated_products}\n'
                f'  Variants created : {created_variants}\n'
                f'  Variants skipped : {skipped} (already existed)\n'
                f'\n  Next steps:\n'
                f'  1. Go to Products and set selling/buying prices\n'
                f'  2. Go to Stock → Adjust to set initial stock quantities\n'
                f'  3. Or use Bulk Upload CSV to set prices in one go\n'
            ))

    @staticmethod
    def _extract_colour(item_name, parent_name):
        """Extract colour code from item name by stripping parent name prefix."""
        # e.g. "Maridadi Fupi-1/33" with parent "Maridadi Fupi" → "1/33"
        name = item_name.strip()
        parent = parent_name.strip()
        if name.lower().startswith(parent.lower()):
            suffix = name[len(parent):].lstrip('-').strip()
            return suffix if suffix else name
        # Fallback: everything after last dash
        if '-' in name:
            return name.rsplit('-', 1)[-1].strip()
        return name
