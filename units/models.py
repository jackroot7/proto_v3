from django.db import models


class UnitOfMeasure(models.Model):
    """
    e.g. Piece, Kg, Litre, Packet, Box, Dozen, Gram, Metre, Pair
    """
    name           = models.CharField(max_length=50, unique=True)
    short_name     = models.CharField(max_length=10)
    allow_decimals = models.BooleanField(
        default=False,
        help_text='Allow fractional quantities (e.g. 0.5 kg). '
                  'Disable for countable items like pieces or packets.'
    )
    is_active  = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Unit of Measure'
        verbose_name_plural = 'Units of Measure'

    def __str__(self):
        return f"{self.name} ({self.short_name})"
