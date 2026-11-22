"""Versioned, append-only fictional invoice catalog for a populated demo.

Together with the four original seed records, this catalog contains 30 invoices.
References stay stable so reloads cannot duplicate or overwrite saved examples.
"""
from datetime import timedelta

from engine import canonical, new_invoice, confirm, finance, settle
from future_value import valuation_today
from opportunities import extra_examples

CATALOG_VERSION = 'fictional-invoice-catalog-v1'
SUPPLIERS = [
    ('Atelier Nova', '123456789'), ('Studio Azur', '234567891'),
    ('Data & Co', '345678912'), ('Orbite Conseil', '456789123'),
    ('Demo Pixel Services', '900000001'), ('Demo Canopée Conseil', '900000002'),
    ('Demo Rivage Solutions', '900000003'), ('Demo Mosaïque Studio', '900000004'),
]
BUYERS = ['Groupe Horizon', 'Maison Atlas', 'Groupe Cobalt',
          'Demo Comptoir Solstice', 'Demo Réseau Méridien', 'Demo Vertex Distribution']
AMOUNTS = [1250, 2400, 3600, 4800, 6200, 7500, 8900, 10500,
           12800, 14200, 16500, 18500, 21000, 24500, 28000, 32000,
           1800, 4200, 9600, 5600, 13500, 7800, 17200, 11200]
HORIZONS = [10, 15, 20, 30, 45, 60, 75, 90, 120]


def builtin_demo_identities():
    """Stable sample identities, independent of dates, amounts and financing edits."""
    rows = [
        ('Atelier Nova', '123456789', 'Groupe Horizon', 'NOV-2026-041'),
        ('Studio Azur', '234567891', 'Groupe Horizon', 'AZ-2026-018'),
        ('Data & Co', '345678912', 'Maison Atlas', 'DC-2026-073'),
        ('Orbite Conseil', '456789123', 'Maison Atlas', 'OC-2026-009'),
        ('Studio Azur', '234567891', 'Maison Atlas', 'DEMO-INVEST-ATLAS'),
        ('Orbite Conseil', '456789123', 'Groupe Cobalt', 'DEMO-INVEST-COBALT'),
    ]
    for index in range(len(AMOUNTS)):
        seller, siren = SUPPLIERS[index % len(SUPPLIERS)]
        rows.append((seller, siren, BUYERS[index % len(BUYERS)], f'DEMO-CATALOG-{index + 1:03d}'))
    return {(siren + ':' + canonical(reference), canonical(seller), canonical(buyer))
            for seller, siren, buyer, reference in rows}


def catalog_examples(existing):
    """Return missing samples only; existing data and outcomes remain authoritative."""
    today = valuation_today()
    additions = extra_examples(existing)
    known = {i['key'] for i in existing + additions}
    for index, amount in enumerate(AMOUNTS):
        seller, siren = SUPPLIERS[index % len(SUPPLIERS)]
        reference = f'DEMO-CATALOG-{index + 1:03d}'
        key = siren + ':' + canonical(reference)
        if key in known:
            continue
        invoice = new_invoice(existing + additions,
            seller=seller, siren=siren, buyer=BUYERS[index % len(BUYERS)],
            reference=reference, amount=amount,
            issued=today-timedelta(days=5 + (index % 6) * 5),
            due=today+timedelta(days=HORIZONS[index % len(HORIZONS)]),
            documents=index != 19, identity=index != 20,
            strength='Average' if index % 4 == 0 else 'Strong',
            history='Occasional delays' if index % 3 == 0 else 'On time')
        if index in (16, 17, 18):
            pass  # Awaiting buyer confirmation.
        elif index == 21:
            confirm(invoice, False, 'Fictional demo: delivery details are disputed.')
        else:
            confirm(invoice, True)
        if index in (22, 23):
            finance(invoice, 3.5, False, 0, annual_interest_rate=6.5,
                    financed_on=today-timedelta(days=7 if index == 22 else 12))
            if index == 23:
                settle(invoice, 'Paid', paid_on=today)
        additions.append(invoice)
        known.add(key)
    return additions
