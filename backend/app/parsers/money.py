"""Conversões de dinheiro partilhadas pelos parsers (nunca `Decimal(float)`)."""

import math
from decimal import Decimal


def cents(v: float) -> Decimal | None:
    """Valor com exatamente até 2 casas, como Decimal exato; None se tiver mais (ou não for finito)."""
    c = v * 100
    if not math.isfinite(c) or abs(c) > 1e15 or abs(c - round(c)) > 1e-6:
        return None
    return Decimal(round(c)).scaleb(-2)
