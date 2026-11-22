"""Ten explicitly requested fictional suppliers; separate from the removed catalog."""
from datetime import timedelta

from engine import canonical, confirm, new_invoice
from future_value import valuation_today

BATCH_VERSION = 'requested-ten-suppliers-v1'
SUPPLIERS = [
    'Démo — Lumen Conseil',
    'Démo — Studio Prisme',
    'Démo — Nacre Digital',
    'Démo — Sillage Design',
    'Démo — Boréal IT',
    'Démo — Plume Communication',
    'Démo — Quartz Data',
    'Démo — Horizon Formation',
    'Démo — Élan Marketing',
    'Démo — Rivage Ingénierie',
]


def requested_supplier_examples(existing):
    """Identical amount/tenor/scenario make rate comparisons easy to explain."""
    today = valuation_today()
    known = {invoice['key'] for invoice in existing}
    result = []
    for index, seller in enumerate(SUPPLIERS, 1):
        siren = f'990000{index:03d}'  # Fictional identifiers; format checks only.
        reference = f'DEMO-PRESTATAIRE-{index:02d}'
        if siren + ':' + canonical(reference) in known:
            continue
        invoice = new_invoice(existing + result, seller=seller, siren=siren,
            buyer='Démo — Client Entreprise', reference=reference, amount=10000,
            issued=today, due=today + timedelta(days=60), documents=True,
            identity=True, strength='Strong', history='On time')
        confirm(invoice, True, 'Fictional example requested for the presentation; checks and buyer confirmation are simulated.')
        invoice['demo_source'] = BATCH_VERSION
        result.append(invoice)
    return result
