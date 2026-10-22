"""Presentation-only formatting for amounts already minimized by the server."""

from decimal import Decimal, InvalidOperation


def format_brl_amount(value: str | None) -> str:
    """Show a visible amount in pt-BR without rounding or changing its source."""
    if value is None:
        return "Campo ausente"
    if value == "":
        return "Campo em branco"
    if value == "[redacted]":
        return "Valor ocultado"
    try:
        amount = Decimal(value)
    except InvalidOperation:
        return "Valor inválido"
    if not amount.is_finite() or len(value) > 64 or amount.adjusted() > 38:
        return "Valor inválido"
    # Preserve sub-cent precision instead of showing a misleading rounded value.
    try:
        if amount != amount.quantize(Decimal("0.01")):
            return value
    except InvalidOperation:
        return value
    formatted = (
        f"{abs(amount):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    )
    return f"{'-' if amount < 0 else ''}R$ {formatted}"
