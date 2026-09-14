"""
Per-register reference generation — INC-0031, INS-0042, COM-0001.

One atomic statement bumps the counter and returns the new value, so two
concurrent saves cannot take the same number. The unique constraint on
(register, ref) is the backstop, not the mechanism.
"""

from sqlalchemy import text

from app.modules.core.shared.extensions import db
from app.modules.hse.lib.registers import register


REF_PAD = 4

_NEXT_VALUE = text("""
    INSERT INTO hse_ref_counters (register, last_value)
    VALUES (:register, 1)
    ON CONFLICT (register) DO UPDATE
        SET last_value = hse_ref_counters.last_value + 1
    RETURNING last_value
""")


def next_ref(register_key):
    """Allocate the next reference for a register. Raises ValueError on an
    unknown key so a typo fails loudly rather than minting a stray prefix."""
    reg = register(register_key)
    if reg is None:
        raise ValueError(f'Unknown register: {register_key}')
    value = db.session.execute(_NEXT_VALUE, {'register': register_key}).scalar_one()
    return format_ref(reg.ref_prefix, value)


def format_ref(prefix, value):
    """PREFIX-0031. Numbers past the pad width simply grow."""
    return f'{prefix}-{str(value).zfill(REF_PAD)}'
