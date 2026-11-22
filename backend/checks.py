"""Deterministic checks: re-do the invoice math in Python.

Language models are great at reading documents but can slip on arithmetic,
so every number check lives here instead.
"""

from datetime import date

from analyzer import InvoiceAnalysis


def _close(a: float, b: float) -> bool:
    # Allow 1 cent (or 0.1% on big amounts) for rounding differences.
    return abs(a - b) <= max(0.01, abs(b) * 0.001)


def _fmt(x: float) -> str:
    return f"{x:,.2f}"


def run_checks(inv: InvoiceAnalysis) -> list[dict]:
    issues: list[dict] = []

    def add(severity: str, category: str, message: str) -> None:
        issues.append({"severity": severity, "category": category, "message": message, "source": "calculated"})

    if not inv.is_invoice:
        return issues

    # 1. Each line: quantity x unit price = amount
    for i, item in enumerate(inv.line_items, start=1):
        if item.quantity is not None and item.unit_price is not None and item.amount is not None:
            expected = item.quantity * item.unit_price
            if not _close(expected, item.amount):
                add(
                    "error",
                    "Line item math",
                    f'Line {i} "{item.description}": {item.quantity:g} x {_fmt(item.unit_price)} = '
                    f"{_fmt(expected)}, but the invoice shows {_fmt(item.amount)}.",
                )

    # 2. Line items add up to the subtotal
    amounts = [item.amount for item in inv.line_items if item.amount is not None]
    if amounts and inv.subtotal is not None and len(amounts) == len(inv.line_items):
        line_sum = sum(amounts)
        if not _close(line_sum, inv.subtotal):
            add(
                "error",
                "Subtotal mismatch",
                f"Line items add up to {_fmt(line_sum)}, but the subtotal shows {_fmt(inv.subtotal)} "
                f"(difference {_fmt(inv.subtotal - line_sum)}).",
            )

    # 3. Subtotal + tax + shipping - discount = total
    base = inv.subtotal if inv.subtotal is not None else (sum(amounts) if amounts else None)
    if base is not None and inv.total is not None:
        expected_total = base + (inv.tax or 0) + (inv.shipping or 0) - abs(inv.discount or 0)
        if not _close(expected_total, inv.total):
            add(
                "error",
                "Total mismatch",
                f"Subtotal + tax + shipping - discount = {_fmt(expected_total)}, "
                f"but the total shows {_fmt(inv.total)} (difference {_fmt(inv.total - expected_total)}).",
            )

    # 4. Tax rate sanity check
    if inv.tax is not None and inv.subtotal and inv.subtotal > 0:
        rate = inv.tax / inv.subtotal * 100
        if inv.tax < 0 or rate > 40:
            add("warning", "Unusual tax", f"Tax is {rate:.1f}% of the subtotal, which looks unusual.")

    # 5. Negative amounts
    if inv.total is not None and inv.total < 0:
        add("warning", "Negative total", "The total is negative - is this a credit note rather than an invoice?")

    # 6. Dates
    inv_date = _parse_date(inv.invoice_date)
    due = _parse_date(inv.due_date)
    if inv_date and due and due < inv_date:
        add("error", "Date", f"Due date ({due}) is before the invoice date ({inv_date}).")
    if inv_date and inv_date > date.today():
        add("warning", "Date", f"Invoice date ({inv_date}) is in the future.")
    if due and due < date.today():
        add("info", "Date", f"This invoice was due on {due} and may be overdue.")

    return issues


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
