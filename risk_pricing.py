"""Auditable two-branch expected-cash-flow pricing, not a calibrated credit score."""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, ROUND_FLOOR, localcontext
import hashlib
import json
import math

from future_value import round_value, valuation_today
from demo_pd import verify_demo_cohort

MODEL_VERSION = 'expected-cashflow-v1'
ORIGINS = ['User-provided, unverified', 'Illustrative assumptions']
NUMERIC_FIELDS = ['annual_pd_percent', 'lgd_percent', 'funding_rate_percent',
                  'capital_charge_percent', 'target_margin_percent', 'upfront_cost',
                  'expected_delay_days', 'recovery_lag_days', 'max_rate_percent', 'max_data_age_days']


def number(value):
    if isinstance(value, bool):
        raise ValueError('Complete every numerical pricing input with a finite value.')
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError('Complete every numerical pricing input with a finite value.') from None
    if not math.isfinite(result):
        raise ValueError('Complete every numerical pricing input with a finite value.')
    return result


def horizon_default_probability(annual_pd_percent, days):
    pd = number(annual_pd_percent) / 100
    duration = number(days)
    if not 0 <= pd < 1 or duration < 0:
        raise ValueError('Annual PD must be at least 0 and below 100%; duration cannot be negative.')
    return -math.expm1(math.log1p(-pd) * duration / 365)


def normalize_assumptions(raw, as_of):
    values = {key: number(raw.get(key)) for key in NUMERIC_FIELDS}
    if not 0 <= values['annual_pd_percent'] < 100 or not 0 <= values['lgd_percent'] <= 100:
        raise ValueError('Annual PD must be below 100%, and LGD must be between 0 and 100%.')
    for key in ['funding_rate_percent', 'capital_charge_percent', 'target_margin_percent', 'max_rate_percent']:
        if not 0 <= values[key] <= 100:
            raise ValueError('Annual cost rates and the investor rate limit must be between 0 and 100%.')
    if values['upfront_cost'] < 0:
        raise ValueError('Upfront transaction costs cannot be negative.')
    for key in ['expected_delay_days', 'recovery_lag_days', 'max_data_age_days']:
        if not values[key].is_integer() or not 0 <= values[key] <= 36500:
            raise ValueError('Delay and data-age limits must be whole days between 0 and 36500.')
        values[key] = int(values[key])
    if raw.get('data_origin') not in ORIGINS or not isinstance(raw.get('source'), str) or not raw['source'].strip():
        raise ValueError('Identify the risk-data origin and source before pricing.')
    try:
        observed = date.fromisoformat(str(raw.get('source_date', '')))
    except ValueError:
        raise ValueError('Enter a valid risk-data observation date.') from None
    if observed > as_of:
        raise ValueError('Risk-data observation date cannot be in the future.')
    values.update(data_origin=raw['data_origin'], source=str(raw['source']).strip()[:500],
                  source_date=observed.isoformat(), notes=str(raw.get('notes', '')).strip()[:2000])
    if raw.get('pd_cohort') is not None:
        values['pd_cohort'] = verify_demo_cohort(raw['pd_cohort'], values['annual_pd_percent'],
                                                values['data_origin'], values['source_date'], as_of)
    return values


def evaluate_cashflows(face, advance, days_to_due, assumptions):
    """All default recoveries are assumed paid after the collection horizon plus lag."""
    horizon = days_to_due + assumptions['expected_delay_days']
    years = horizon / 365
    probability = horizon_default_probability(assumptions['annual_pd_percent'], horizon)
    effective = sum(assumptions[k] for k in ['funding_rate_percent', 'capital_charge_percent',
                                            'target_margin_percent']) / 100
    base = math.log1p(effective)
    recovery = 1 - assumptions['lgd_percent'] / 100
    payment_pv = (1 - probability) * face * math.exp(-base * years)
    recovery_pv = probability * recovery * advance * math.exp(
        -base * (years + assumptions['recovery_lag_days'] / 365))
    return {'horizon_days': horizon, 'years': years, 'horizon_pd': probability,
            'base_rate_percent': base * 100, 'base_effective_rate_percent': effective * 100,
            'survival_payment_pv': payment_pv,
            'recovery_pv': recovery_pv,
            'expected_npv': payment_pv + recovery_pv - advance - assumptions['upfront_cost'],
            'expected_credit_loss': probability * assumptions['lgd_percent'] / 100 * advance}


def price_invoice(invoice, raw_assumptions, as_of=None):
    as_of = as_of or valuation_today()
    face = number(invoice['amount'])
    due = date.fromisoformat(invoice['due'])
    days = (due - as_of).days
    if face <= 0 or days <= 0:
        raise ValueError('Risk pricing requires a positive invoice amount and a future due date.')
    assumptions = normalize_assumptions(raw_assumptions, as_of)
    values = evaluate_cashflows(face, 1, days, assumptions)
    probability, years = values['horizon_pd'], values['years']
    unit_recovery_pv = values['recovery_pv']
    denominator = 1 - unit_recovery_pv
    numerator = values['survival_payment_pv'] - assumptions['upfront_cost']
    blockers = []
    if (as_of - date.fromisoformat(assumptions['source_date'])).days > assumptions['max_data_age_days']:
        blockers.append('Risk data exceed the configured maximum age.')
    advance = annual = discount = None
    if denominator <= 0 or numerator <= 0:
        blockers.append('Expected discounted receipts do not cover transaction costs.')
    else:
        exact = numerator / denominator
        # Never round an offer up beyond the model's maximum affordable advance.
        with localcontext() as context:
            context.prec = 340
            advance = float(Decimal(str(exact)).quantize(Decimal('0.01'), rounding=ROUND_FLOOR))
        if advance < 1 or advance > face:
            blockers.append('The model cannot produce an advance between EUR 1 and the invoice amount.')
            advance = None
        else:
            annual = 100 * math.log(face / advance) / years
            discount = 100 * (face - advance) / face
            if annual > assumptions['max_rate_percent']:
                blockers.append('Calculated annual rate exceeds the investor policy limit.')
    cashflows = evaluate_cashflows(face, advance or 0, days, assumptions)
    if advance is None:
        cashflows.update(expected_npv=None, expected_credit_loss=None, recovery_pv=None)
    report = {
        'model_version': MODEL_VERSION,
        'invoice': {key: invoice[key] for key in ['id', 'reference', 'seller', 'siren', 'buyer', 'amount', 'due']},
        'priced_on': as_of.isoformat(), 'assumptions': assumptions,
        'days_to_due': days, 'expected_payment_on': (due + timedelta(days=assumptions['expected_delay_days'])).isoformat(),
        'advance': advance, 'gross_discount': round_value(face - advance) if advance else None,
        'discount_percent': discount, 'annual_rate_percent': annual,
        'acceptable': not blockers, 'blockers': blockers, **cashflows,
    }
    from commission import add_commission
    add_commission(report)
    canonical = json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False)
    report['snapshot_hash'] = hashlib.sha256(canonical.encode()).hexdigest()
    return report


def stress_scenarios(invoice, assumptions, as_of=None):
    """Mechanical sensitivity; the source assumptions remain unchanged."""
    base = price_invoice(invoice, assumptions, as_of)
    scenarios = [('Base assumptions', {}),
                 ('Annual PD doubled', {'annual_pd_percent': min(number(assumptions['annual_pd_percent']) * 2, 99.9)}),
                 ('LGD +10 percentage points', {'lgd_percent': min(number(assumptions['lgd_percent']) + 10, 100)}),
                 ('Payment delayed by 30 more days', {'expected_delay_days': min(int(number(assumptions['expected_delay_days'])) + 30, 36500)})]
    results = []
    for label, change in scenarios:
        altered = dict(deepcopy(assumptions), **change)
        if change:
            # Stress assumptions are hypothetical deviations, not observed cohort PDs.
            altered.pop('pd_cohort', None)
        report = price_invoice(invoice, altered, as_of)
        npv = (evaluate_cashflows(invoice['amount'], base['advance'], report['days_to_due'],
                                  report['assumptions'])['expected_npv'] if base['advance'] else None)
        results.append({'scenario': label, 'advance': report['advance'],
                        'annual_rate_percent': report['annual_rate_percent'],
                        'npv_at_base_advance': npv, 'acceptable': report['acceptable']})
    return results
