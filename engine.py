"""Demo rules, with no connection to financial services."""
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import re
import unicodedata
from uuid import uuid4


def money(value):
    return float(Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def canonical(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value).casefold() if c.isalnum())


def quote(amount, rate):
    if amount <= 0 or not 0 <= rate < 100:
        raise ValueError('Invalid amount or rate.')
    fee = money(Decimal(str(amount)) * Decimal(str(rate)) / 100)
    return {'amount': money(amount), 'fee': fee, 'advance': money(Decimal(str(amount)) - Decimal(str(fee)))}


def score(invoice):
    # Transparent educational score; no probability of default estimated.
    points = {'Debtor financial strength (declared)': {'Strong': 40, 'Average': 25, 'Weak': 5}[invoice['strength']],
              'Payment history (declared)': {'On time': 25, 'Occasional delays': 15, 'Frequent delays': 0}[invoice['history']],
              'Buyer confirmation': 25 if invoice['buyer_status'] == 'Confirmed' else 0,
              'Complete documents (declared)': 10 if invoice['documents'] else 0}
    return sum(points.values()), points


def new_invoice(invoices, *, seller, siren, buyer, reference, amount, issued, due,
                documents, identity, strength, history, file_bytes=b'', filename=''):
    if not seller.strip() or not buyer.strip() or not reference.strip():
        raise ValueError('Enter the supplier, buyer and reference.')
    if canonical(seller) == canonical(buyer):
        raise ValueError('The supplier and buyer must be different.')
    if not re.fullmatch(r'\d{9}', siren):
        raise ValueError('The SIREN must contain 9 digits (format check only).')
    if issued > date.today() or due <= date.today() or due < issued:
        raise ValueError("The issue date must be today or earlier and the due date must be in the future.")
    quote(amount, 3)
    key = f'{siren}:{canonical(reference)}'
    digest = hashlib.sha256(file_bytes).hexdigest() if file_bytes else ''
    if any(i['key'] == key or (digest and digest == i['file_hash']) for i in invoices):
        raise ValueError('Duplicate detected: supplier reference or file already submitted in this workspace.')
    payload = {'siren': siren, 'reference': canonical(reference), 'amount': money(amount), 'due': due.isoformat(), 'buyer': canonical(buyer)}
    return dict(id=uuid4().hex[:8].upper(), key=key, seller=seller.strip(), siren=siren, buyer=buyer.strip(),
                reference=reference.strip(), amount=money(amount), issued=issued.isoformat(), due=due.isoformat(),
                documents=documents, identity=identity, strength=strength, history=history,
                file_hash=digest, filename=filename,
                record_hash=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
                buyer_status='Pending', status='To review', note='', financing=None, outcome=None)


def financing_checks(i):
    """One source of truth for eligibility and its human-readable explanations."""
    value, _ = score(i)
    processed = i['status'] in ('Financed', 'Closed') or i.get('financing') is not None
    disputed = i['buyer_status'] == 'Disputed' or i['status'] == 'Disputed'
    return [
        ('Available for financing', not processed,
         'This invoice has already been financed or closed.'),
        ('Buyer confirmation', i['buyer_status'] == 'Confirmed',
         'The invoice is disputed by the buyer.' if disputed else 'Buyer confirmation is missing.'),
        ('SME identity', bool(i['identity']), 'SME identity verification is incomplete.'),
        ('Complete documents (declared)', bool(i['documents']),
         'Supporting documents are incomplete: invoice, purchase order or proof of delivery.'),
        ('Future due date', date.fromisoformat(i['due']) > date.today(),
         'The due date has been reached or has passed.'),
        ('Demo score at least 65/100', value >= 65,
         'The demo score is below 65/100. Manual review is required; financing stays blocked.'),
        ('Invoice approval', i['status'] == 'Approved',
         'Invoice approval is incomplete.'),
    ]


def financing_blockers(i):
    return [message for _, passed, message in financing_checks(i) if not passed]


def eligible(i):
    return not financing_blockers(i)


def complete_checks(i, identity, documents):
    if i['status'] in ('Financed', 'Closed') or i.get('financing'):
        raise ValueError('A financed or closed invoice cannot be changed.')
    i.update(identity=bool(identity), documents=bool(documents))


def journey(i):
    funded = bool(i.get('financing'))
    return [
        ('Submitted', True),
        ('Confirmed', funded or i['buyer_status'] == 'Confirmed'),
        ('Eligible', funded or eligible(i)),
        ('Financed', funded),
        ('Paid', i.get('outcome') == 'Paid'),
    ]


def confirm(i, approved, note=''):
    if i['status'] in ('Financed', 'Closed'):
        raise ValueError('A financed or closed invoice cannot be changed.')
    if not approved and not note.strip():
        raise ValueError('Provide a reason for the dispute.')
    i.update(buyer_status='Confirmed' if approved else 'Disputed', status='Approved' if approved else 'Disputed', note=note.strip())


def finance(i, rate, recourse, coverage):
    if not eligible(i):
        raise ValueError('This invoice does not meet the demo financing requirements.')
    if not 0 <= coverage <= 100:
        raise ValueError('Invalid coverage.')
    i.update(status='Financed', financing={**quote(i['amount'], rate), 'rate': rate, 'recourse': recourse, 'coverage': coverage})


def loss_scenario(amount, rate, coverage, recourse=False):
    q = quote(amount, rate)
    # Assumption: indemnity based on face value, capped at the capital advanced.
    indemnity = min(q['advance'], money(Decimal(str(amount)) * Decimal(str(coverage)) / 100))
    residual = money(q['advance'] - indemnity)
    return {**q, 'indemnity': indemnity, 'residual': residual,
            'supplier_claim': residual if recourse else 0.0,
            'lender_exposure': residual}


def settle(i, outcome):
    if i['status'] != 'Financed':
        raise ValueError('Only a financed invoice can be tracked or closed.')
    if outcome not in ('Paid', 'Late payment', 'Insolvency', 'Dispute'):
        raise ValueError('Unknown event.')
    i['outcome'] = outcome
    if outcome == 'Paid':
        i['status'] = 'Closed'


def seed():
    today = date.today()
    invoices = []
    for seller, siren, buyer, ref, amount, days, strength, history in [
        ('Atelier Nova', '123456789', 'Groupe Horizon', 'NOV-2026-041', 15000, 45, 'Strong', 'On time'),
        ('Studio Azur', '234567891', 'Groupe Horizon', 'AZ-2026-018', 8200, 30, 'Strong', 'Occasional delays'),
        ('Data & Co', '345678912', 'Maison Atlas', 'DC-2026-073', 24000, 60, 'Average', 'On time'),
        ('Orbite Conseil', '456789123', 'Maison Atlas', 'OC-2026-009', 6400, 20, 'Weak', 'Frequent delays')]:
        invoices.append(new_invoice(invoices, seller=seller, siren=siren, buyer=buyer, reference=ref, amount=amount,
                         issued=today-timedelta(days=5), due=today+timedelta(days=days), documents=True,
                         identity=True, strength=strength, history=history))
    confirm(invoices[0], True)
    confirm(invoices[2], True)
    finance(invoices[2], 3, False, 80)
    confirm(invoices[3], False, 'Service details need clarification in this fictional scenario.')
    return invoices


def migrate_session(invoices):
    """Upgrade French enum values in an existing session without losing user data."""
    legacy = {
        'Solide': 'Strong', 'Intermédiaire': 'Average', 'Fragile': 'Weak',
        'Ponctuel': 'On time', 'Retards occasionnels': 'Occasional delays',
        'Retards fréquents': 'Frequent delays', 'En attente': 'Pending',
        'À vérifier': 'To review', 'Validée': 'Approved', 'Confirmée': 'Confirmed',
        'Contestée': 'Disputed', 'Financée': 'Financed', 'Clôturée': 'Closed',
        'Payée': 'Paid', 'Retard': 'Late payment', 'Insolvabilité': 'Insolvency', 'Litige': 'Dispute',
    }
    for invoice in invoices:
        for field in ('strength', 'history', 'buyer_status', 'status', 'outcome'):
            value = invoice.get(field)
            if value in legacy:
                invoice[field] = legacy[value]
        if invoice.get('note') == 'Prestation à clarifier dans ce scénario fictif.':
            invoice['note'] = 'Service details need clarification in this fictional scenario.'
