"""Portfolio totals from saved advances and simulated full payments only."""
from datetime import date

from engine import canonical, money
from future_value import valuation_today


def holding_yield_percent(face, advance):
    """Gross return on the capital advanced, conditional on full payment."""
    return 100 * (face - advance) / advance


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
                repayments=money(sum(i['amount'] for i in paid)),
                realized_gain=money(sum(i['amount'] - i['financing']['advance'] for i in paid)),
                potential_gain=money(sum(i['amount'] - i['financing']['advance'] for i in active)),
                overdue_capital=money(sum(i['financing']['advance'] for i in overdue)),
                overdue_count=len(overdue), exposure=exposure,
                overdue=sorted(overdue, key=lambda i: (i['due'], i['reference'])))
