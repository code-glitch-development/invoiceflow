"""Continuous-interest simulation, independent from fees and actual cash flows."""
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP, localcontext
import math
from zoneinfo import ZoneInfo


def valuation_today():
    return datetime.now(ZoneInfo('Europe/Paris')).date()


def continuous_future_value(previous_value, years, annual_rate_percent):
    """P * exp(t * r / 100); return unrounded value to avoid repeated rounding."""
    try:
        principal, duration, rate = map(float, (previous_value, years, annual_rate_percent))
    except (ValueError, TypeError, OverflowError):
        raise ValueError('Enter a valid capital, duration and annual interest rate.') from None
    if not all(math.isfinite(v) for v in (principal, duration, rate)) or principal < 0 or duration < 0 or not 0 <= rate <= 100:
        raise ValueError('Capital and duration must be non-negative; the annual interest rate must be between 0 and 100%.')
    if principal == 0:
        return 0.0
    try:
        value = principal * math.exp(duration * rate / 100)
    except OverflowError:
        raise ValueError('The future value is too large. Reduce the capital, rate or duration.') from None
    if not math.isfinite(value):
        raise ValueError('The future value is too large. Reduce the capital, rate or duration.')
    return value


def round_value(value):
    with localcontext() as context:
        context.prec = 340  # Enough for any finite float, including cent rounding.
        return float(Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def investor_valuation(invoice, as_of=None):
    """Always start from the original advance; rendering twice cannot add interest."""
    funding = invoice.get('financing')
    if not funding or not funding.get('financed_on') or 'annual_interest_rate' not in funding:
        return None
    if invoice.get('outcome') == 'Paid' and not funding.get('paid_on'):
        return None
    start = date.fromisoformat(funding['financed_on'])
    requested = as_of or valuation_today()
    if requested < start:
        raise ValueError('The valuation date cannot be before the financing date.')
    end = requested
    if invoice.get('outcome') == 'Paid':
        paid = date.fromisoformat(funding['paid_on'])
        if paid < start:
            raise ValueError('The payment date cannot be before the financing date.')
        end = min(requested, paid)
    days = (end - start).days
    years = days / 365.0
    capital = funding['advance']
    value = continuous_future_value(capital, years, funding['annual_interest_rate'])
    return {'principal': capital, 'annual_rate': funding['annual_interest_rate'],
            'start': start.isoformat(), 'end': end.isoformat(), 'days': days, 'years': years,
            'future_value': round_value(value), 'interest': round_value(value - capital),
            'stopped_at_payment': invoice.get('outcome') == 'Paid' and requested >= paid}
