"""
Turns a stored money figure into a Decimal.

Project.value is a Float but the CS finance fields are Numeric, so mixing them
in a sum raises TypeError. All money totals in this module go through here.
"""
from decimal import Decimal


def money(value):
    """`value` as a Decimal; None counts as zero. Floats go via str so the
    Decimal matches the written figure, not the binary float."""
    if value is None:
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
