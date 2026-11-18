"""Règles du démonstrateur, sans connexion à des services financiers."""
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
        raise ValueError('Montant ou taux invalide.')
    fee = money(Decimal(str(amount)) * Decimal(str(rate)) / 100)
    return {'amount': money(amount), 'fee': fee, 'advance': money(Decimal(str(amount)) - Decimal(str(fee)))}


def score(invoice):
    # Barème pédagogique transparent ; aucune probabilité de défaut estimée.
    points = {'Solidité du débiteur (déclarée)': {'Solide': 40, 'Intermédiaire': 25, 'Fragile': 5}[invoice['strength']],
              'Historique de paiement (déclaré)': {'Ponctuel': 25, 'Retards occasionnels': 15, 'Retards fréquents': 0}[invoice['history']],
              'Confirmation du client': 25 if invoice['buyer_status'] == 'Confirmée' else 0,
              'Pièces complètes (déclarées)': 10 if invoice['documents'] else 0}
    return sum(points.values()), points


def new_invoice(invoices, *, seller, siren, buyer, reference, amount, issued, due,
                documents, identity, strength, history, file_bytes=b'', filename=''):
    if not seller.strip() or not buyer.strip() or not reference.strip():
        raise ValueError('Renseignez le fournisseur, le client et la référence.')
    if canonical(seller) == canonical(buyer):
        raise ValueError('Le fournisseur et le client doivent être différents.')
    if not re.fullmatch(r'\d{9}', siren):
        raise ValueError('Le SIREN doit contenir 9 chiffres (format uniquement).')
    if issued > date.today() or due <= date.today() or due < issued:
        raise ValueError("La date d’émission doit être passée ou actuelle et l’échéance future.")
    quote(amount, 3)
    key = f'{siren}:{canonical(reference)}'
    digest = hashlib.sha256(file_bytes).hexdigest() if file_bytes else ''
    if any(i['key'] == key or (digest and digest == i['file_hash']) for i in invoices):
        raise ValueError('Doublon détecté : référence fournisseur ou fichier déjà déposé dans cette session.')
    payload = {'siren': siren, 'reference': canonical(reference), 'amount': money(amount), 'due': due.isoformat(), 'buyer': canonical(buyer)}
    return dict(id=uuid4().hex[:8].upper(), key=key, seller=seller.strip(), siren=siren, buyer=buyer.strip(),
                reference=reference.strip(), amount=money(amount), issued=issued.isoformat(), due=due.isoformat(),
                documents=documents, identity=identity, strength=strength, history=history,
                file_hash=digest, filename=filename,
                record_hash=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
                buyer_status='En attente', status='À vérifier', note='', financing=None, outcome=None)


def eligible(i):
    value, _ = score(i)
    return (i['status'] == 'Validée' and i['buyer_status'] == 'Confirmée' and i['documents']
            and i['identity'] and value >= 65 and date.fromisoformat(i['due']) > date.today())


def confirm(i, approved, note=''):
    if i['status'] in ('Financée', 'Clôturée'):
        raise ValueError('Une facture financée ou clôturée ne peut plus être modifiée.')
    if not approved and not note.strip():
        raise ValueError('Précisez le motif de contestation.')
    i.update(buyer_status='Confirmée' if approved else 'Contestée', status='Validée' if approved else 'Contestée', note=note.strip())


def finance(i, rate, recourse, coverage):
    if not eligible(i):
        raise ValueError('Cette facture ne remplit pas les conditions de financement de la démo.')
    if not 0 <= coverage <= 100:
        raise ValueError('Couverture invalide.')
    i.update(status='Financée', financing={**quote(i['amount'], rate), 'rate': rate, 'recourse': recourse, 'coverage': coverage})


def loss_scenario(amount, rate, coverage, recourse=False):
    q = quote(amount, rate)
    # Hypothèse : indemnisation sur la valeur nominale, plafonnée au capital avancé.
    indemnity = min(q['advance'], money(Decimal(str(amount)) * Decimal(str(coverage)) / 100))
    residual = money(q['advance'] - indemnity)
    return {**q, 'indemnity': indemnity, 'residual': residual,
            'supplier_claim': residual if recourse else 0.0,
            'lender_exposure': residual}


def settle(i, outcome):
    if i['status'] != 'Financée':
        raise ValueError('Seule une facture financée peut être suivie ou clôturée.')
    if outcome not in ('Payée', 'Retard', 'Insolvabilité', 'Litige'):
        raise ValueError('Événement inconnu.')
    i['outcome'] = outcome
    if outcome == 'Payée':
        i['status'] = 'Clôturée'


def seed():
    today = date.today()
    invoices = []
    for seller, siren, buyer, ref, amount, days, strength, history in [
        ('Atelier Nova', '123456789', 'Groupe Horizon', 'NOV-2026-041', 15000, 45, 'Solide', 'Ponctuel'),
        ('Studio Azur', '234567891', 'Groupe Horizon', 'AZ-2026-018', 8200, 30, 'Solide', 'Retards occasionnels'),
        ('Data & Co', '345678912', 'Maison Atlas', 'DC-2026-073', 24000, 60, 'Intermédiaire', 'Ponctuel'),
        ('Orbite Conseil', '456789123', 'Maison Atlas', 'OC-2026-009', 6400, 20, 'Fragile', 'Retards fréquents')]:
        invoices.append(new_invoice(invoices, seller=seller, siren=siren, buyer=buyer, reference=ref, amount=amount,
                         issued=today-timedelta(days=5), due=today+timedelta(days=days), documents=True,
                         identity=True, strength=strength, history=history))
    confirm(invoices[0], True)
    confirm(invoices[2], True)
    finance(invoices[2], 3, False, 80)
    confirm(invoices[3], False, 'Prestation à clarifier dans ce scénario fictif.')
    return invoices
