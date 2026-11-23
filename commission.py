"""One-off platform commission, separate from investor principal and return."""
from decimal import Decimal, ROUND_HALF_UP
import math

COMMISSION_PERCENT = 1.0


def commission_breakdown(face, advance):
    face, advance = Decimal(str(face)), Decimal(str(advance))
    if not all(math.isfinite(float(v)) and v > 0 for v in (face, advance)) or advance > face:
        raise ValueError('Invalid amount or rate.')
    cent = Decimal('0.01')
    fee = (face * Decimal(str(COMMISSION_PERCENT)) / 100).quantize(cent, rounding=ROUND_HALF_UP)
    net = (advance - fee).quantize(cent, rounding=ROUND_HALF_UP)
    if net <= 0:
        raise ValueError('The InvoiceFlow commission leaves no positive net payment to the SME.')
    return dict(commission_policy='invoiceflow-one-off-v1', platform_commission_percent=COMMISSION_PERCENT,
                platform_commission=float(fee), sme_net_proceeds=float(net),
                total_sme_cost=float((face - net).quantize(cent, rounding=ROUND_HALF_UP)))


def add_commission(report):
    """Enrich a fresh pricing report before hashing; never reprice saved reports."""
    if report['advance'] is not None:
        try:
            report.update(commission_breakdown(report['invoice']['amount'], report['advance']))
        except ValueError as exc:
            report['acceptable'] = False
            report['blockers'].append(str(exc))
    return report
