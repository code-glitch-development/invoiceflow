"""Portfolio totals from saved advances and simulated full payments only."""
from datetime import date
import math

from engine import canonical, money
from future_value import valuation_today


def holding_yield_percent(face, advance):
    """Gross return on the capital advanced, conditional on full payment."""
    return 100 * (face - advance) / advance


def financed_annual_rate(invoice):
    """Original continuous equivalent from cash-flow terms, not the interest sandbox."""
    funding = invoice['financing']
    pricing = funding.get('pricing') or {}
    try:
        start = date.fromisoformat(funding['financed_on'])
        end = date.fromisoformat(pricing.get('expected_payment_on') or invoice['due'])
        days = (end - start).days
        advance, face = float(funding['advance']), float(invoice['amount'])
        if days <= 0 or not all(math.isfinite(n) and n > 0 for n in (advance, face)):
            return None
        return 100 * math.log(face / advance) * 365 / days
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def portfolio_summary(invoices, as_of=None):
    today = as_of or valuation_today()
    active, paid = [], []
    for invoice in invoices:
        if not invoice.get('financing'):
            continue
        if invoice.get('outcome') == 'Paid':
            paid.append(invoice)
        elif invoice['status'] == 'Financed':
            active.append(invoice)
    overdue = [i for i in active if date.fromisoformat(i['due']) < today
               or i.get('outcome') == 'Late payment']
    total = money(sum(i['financing']['advance'] for i in active))
    paid_capital = money(sum(i['financing']['advance'] for i in paid))
    invested = money(total + paid_capital)
    realized = money(sum(i['amount'] - i['financing']['advance'] for i in paid))
    potential = money(sum(i['amount'] - i['financing']['advance'] for i in active))
    projected_gain = money(realized + potential)
    annual_rates = [(i['financing']['advance'], financed_annual_rate(i)) for i in active]
    missing_rates = sum(rate is None for _, rate in annual_rates)
    annual = (sum(capital * rate for capital, rate in annual_rates) / total
              if total > 0 and not missing_rates else None)
    groups = {}
    for invoice in active:
        group = groups.setdefault(canonical(invoice['buyer']),
                                  dict(buyer=invoice['buyer'], capital=0.0, count=0))
        group['capital'] += invoice['financing']['advance']
        group['count'] += 1
    exposure = []
    for group in groups.values():
        capital = money(group['capital'])
        exposure.append(dict(group, capital=capital, share_percent=100 * capital / total if total else 0.0))
    exposure.sort(key=lambda row: (-row['capital'], row['buyer']))
    return dict(outstanding_capital=total,
                total_capital_advanced=invested, projected_gross_gain=projected_gain,
                projected_return_percent=100 * projected_gain / invested if invested > 0 else None,
                realized_return_percent=100 * realized / paid_capital if paid_capital > 0 else None,
                weighted_annual_rate_percent=annual, annual_missing_count=missing_rates,
                repayments=money(sum(i['amount'] for i in paid)),
                realized_gain=realized, potential_gain=potential,
                overdue_capital=money(sum(i['financing']['advance'] for i in overdue)),
                overdue_count=len(overdue), exposure=exposure,
                overdue=sorted(overdue, key=lambda i: (i['due'], i['reference'])))
