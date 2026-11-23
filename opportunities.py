"""Pure investor discovery and review calculations, using the existing pricing engine."""
from copy import deepcopy
import hashlib
import json
import math
from datetime import timedelta

from demo_pd import demo_cohort
from financial_risk import assess_buyer
from engine import canonical, eligible, new_invoice, confirm, money
from future_value import valuation_today
from risk_pricing import price_invoice

SCENARIOS = {
    'Prudent': 'Simulated on-time buyers',
    'Central': 'All simulated buyers',
    'Stressed': 'Simulated frequently late buyers',
}
DEFAULT_COSTS = dict(lgd_percent=60.0, funding_rate_percent=3.0,
    capital_charge_percent=1.0, target_margin_percent=2.0, upfront_cost=20.0,
    expected_delay_days=5, recovery_lag_days=90, max_rate_percent=100.0,
    max_data_age_days=365)


def buyer_scenario(buyer, assignments):
    defaults = {canonical('Maison Atlas'): 'Prudent', canonical('Groupe Cobalt'): 'Stressed'}
    return assignments.get(canonical(buyer), defaults.get(canonical(buyer), 'Central'))


def assumptions_for(scenario, costs=None):
    cohort = demo_cohort(SCENARIOS[scenario])
    return dict(DEFAULT_COSTS | (costs or {}),
        annual_pd_percent=cohort['observed_pd_percent'], pd_cohort=cohort,
        data_origin='Illustrative assumptions',
        source=cohort['dataset_version'] + ' / ' + cohort['group'],
        source_date=cohort['observation_end'],
        notes='Fictional demonstration scenario; nominal recoveries before discounting.')


def opportunities(invoices, assignments=None, costs=None):
    result = []
    for invoice in invoices:
        if not eligible(invoice) or assess_buyer(invoice)['value'] is None:
            continue
        scenario = buyer_scenario(invoice['buyer'], assignments or {})
        report = price_invoice(invoice, assumptions_for(scenario, costs))
        result.append(dict(invoice=invoice, scenario=scenario, report=report))
    return result


def filtered(entries, budget, horizon, scenario='All'):
    return [e for e in entries if e['report']['acceptable'] and
            e['report']['advance'] <= budget and e['report']['horizon_days'] <= horizon and
            (scenario == 'All' or e['scenario'] == scenario)]


def review_selection(entries, selected_ids, budget, portfolio):
    if not math.isfinite(budget) or budget <= 0:
        raise ValueError('Enter a positive budget.')
    if not 1 <= len(selected_ids) <= 3 or len(set(selected_ids)) != len(selected_ids):
        raise ValueError('Select between one and three different invoices.')
    available = {e['invoice']['id']: e for e in entries}
    chosen = []
    for identifier in selected_ids:
        if identifier not in available or not available[identifier]['report']['acceptable']:
            raise ValueError('The selection changed. Review the latest offers before confirming.')
        chosen.append(available[identifier])
    total = money(sum(e['report']['advance'] for e in chosen))
    if total > budget:
        raise ValueError('The total advance exceeds your budget.')
    return dict(rows=deepcopy(chosen), budget=budget, advance=total,
                gross_gain=money(sum(e['report']['gross_discount'] for e in chosen)),
                repayment=money(sum(e['invoice']['amount'] for e in chosen)),
                versions={i['id']: i.get('_version') for i in portfolio})


def review_fingerprint(review):
    return hashlib.sha256(json.dumps(review, sort_keys=True, allow_nan=False).encode()).hexdigest()


def extra_examples(existing):
    """Append-only samples: never replace a visitor's invoices or confirmations."""
    today = valuation_today()
    result = []
    for seller, siren, buyer, reference, days in [
        ('Studio Azur', '234567891', 'Maison Atlas', 'DEMO-INVEST-ATLAS', 60),
        ('Orbite Conseil', '456789123', 'Groupe Cobalt', 'DEMO-INVEST-COBALT', 30),
    ]:
        key = siren + ':' + canonical(reference)
        if any(i['key'] == key for i in existing):
            continue
        invoice = new_invoice(existing + result, seller=seller, siren=siren, buyer=buyer,
            reference=reference, amount=5000, issued=today-timedelta(days=5),
            due=today+timedelta(days=days), documents=True, identity=True,
            strength='Strong', history='On time')
        confirm(invoice, True)
        result.append(invoice)
    return result
