"""Unit conversion between what is stored (kg, cm) and what a user sees and types."""
from decimal import ROUND_HALF_UP, Decimal

from .models import UserSettings

KG_PER_LB = Decimal('0.45359237')
CM_PER_INCH = Decimal('2.54')


class Units:
    def __init__(self, weight=UserSettings.WeightUnit.KG, length=UserSettings.LengthUnit.CM):
        self.weight = weight
        self.length = length

    @classmethod
    def for_user(cls, user):
        settings = UserSettings.objects.filter(user=user).first()
        if settings is None:
            return cls()
        return cls(settings.weight_unit, settings.length_unit)

    @property
    def uses_lb(self):
        return self.weight == UserSettings.WeightUnit.LB

    @property
    def uses_inches(self):
        return self.length == UserSettings.LengthUnit.FT_IN

    @property
    def weight_label(self):
        return 'lb' if self.uses_lb else 'kg'

    @property
    def length_label(self):
        return 'in' if self.uses_inches else 'cm'

    def weight_out(self, kg):
        if kg is None:
            return None
        kg = Decimal(str(kg))
        return kg / KG_PER_LB if self.uses_lb else kg

    def weight_in(self, value, places=2):
        if value is None:
            return None
        value = Decimal(str(value))
        kg = value * KG_PER_LB if self.uses_lb else value
        return kg.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)

    def length_out(self, cm):
        if cm is None:
            return None
        cm = Decimal(str(cm))
        return cm / CM_PER_INCH if self.uses_inches else cm

    def length_in(self, value, places=1):
        if value is None:
            return None
        value = Decimal(str(value))
        cm = value * CM_PER_INCH if self.uses_inches else value
        return cm.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
