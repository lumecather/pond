from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def num(value, sig=4):
    """A number without trailing zeros: big ones with thousands separators, small ones with `sig` significant digits."""
    if value in (None, ""):
        return "—"
    try:
        d = Decimal(str(value))
    except InvalidOperation:
        return value
    if d == 0:
        return "0"
    a = abs(d)
    if a >= 1000:
        return f"{d:,.0f}"
    if a >= 1:
        s = f"{d:.2f}" if a >= 100 else f"{d:.4f}"
    else:
        s = f"{d:.{min(-a.adjusted() - 1 + int(sig), 18)}f}"
    return s.rstrip("0").rstrip(".")


@register.filter
def usd(value):
    if value in (None, ""):
        return "—"
    text = num(value)
    return f"-${text[1:]}" if text.startswith("-") else f"${text}"


@register.filter
def compact(value):
    """A dollar amount in short form: $834K, $11.3M."""
    if value in (None, ""):
        return "—"
    v = float(value)
    for limit, name in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(v) >= limit:
            return f"${v / limit:.3g}{name}"
    return f"${v:.0f}"


@register.filter
def slippage(bps):
    return f"{int(bps) / 100:g} %"


@register.filter
def hue(text):
    """Hue for a token's avatar circle: the same symbol always gets the same color."""
    return sum(ord(ch) * (i + 3) for i, ch in enumerate(str(text))) % 360


@register.filter
def short(address):
    a = str(address or "")
    return f"{a[:6]}…{a[-4:]}" if len(a) > 12 else a
