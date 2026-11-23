"""User-chosen demonstration tariff. No statistical Z-to-PD calibration is claimed."""
from datetime import date
from decimal import Decimal, ROUND_FLOOR
from hashlib import sha256
import json
import math
from financial_risk import assess_buyer
from future_value import valuation_today

MODEL_VERSION='altman-tariff-demo-v1'
POLICY={'base_percent':5.0,'grey_premium_pp':2.0,'distress_premium_pp':4.0,'missing_accounts_premium_pp':5.0}


def tariff_quote(invoice,as_of=None):
    today=as_of or valuation_today()
    risk=assess_buyer(invoice,today)
    z=risk['value'];blockers=[]
    if z is None:
        premium=POLICY['missing_accounts_premium_pp'];scenario='Unknown'
        if invoice.get('buyer_accounts'):
            blockers.append('The supplied accounts are unusable. Correct the document or request manual review before financing.')
    elif z<1.1:
        premium=POLICY['distress_premium_pp'];scenario='Stressed'
        blockers.append('A distressed accounting score requires manual review. The displayed tariff is indicative only.')
    elif z<=2.6:premium=POLICY['grey_premium_pp'];scenario='Central'
    else:premium=0.0;scenario='Prudent'
    rate=POLICY['base_percent']+premium
    days=(date.fromisoformat(invoice['due'])-today).days
    face=float(invoice['amount'])
    if not math.isfinite(face) or face<=0 or days<=0:raise ValueError('A positive invoice amount and future due date are required for tariff pricing.')
    exact=face*math.exp(-(rate/100)*(days/365))
    advance=float(Decimal(str(exact)).quantize(Decimal('0.01'),rounding=ROUND_FLOOR))
    if advance<1:raise ValueError('The tariff cannot produce an advance of at least EUR 1.')
    actual=100*math.log(face/advance)*365/days
    report=dict(model_version=MODEL_VERSION,priced_on=today.isoformat(),invoice={key:invoice[key] for key in ['id','reference','seller','siren','buyer','amount','due']},
        scenario=scenario,accounting_z=z,accounting_status=risk['band'],
        assumptions=dict(policy=POLICY.copy(),origin='User-chosen demonstration tariff, not calibrated to default losses',day_count='Actual/365 fixed',compounding='continuous'),
        policy_annual_rate_percent=rate,base_rate_percent=POLICY['base_percent'],risk_premium_pp=premium,
        advance=advance,gross_discount=round(face-advance,2),discount_percent=100*(face-advance)/face,
        annual_rate_percent=actual,horizon_days=days,expected_payment_on=invoice['due'],
        acceptable=not blockers,blockers=blockers,source_accounting_document=risk.get('document'))
    report['snapshot_hash']=sha256(json.dumps(report,sort_keys=True,allow_nan=False).encode()).hexdigest()
    return report
