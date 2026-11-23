"""Named demo suppliers and view filtering, without seeded invoices or authentication."""
from engine import canonical

ALL_SMES = 'All SME companies (demo)'
DEMO_SMES = {
    'Atelier Nova Conseil SAS': '123456789',
    'Orbe Digital SAS': '234567890',
    'Studio Prisme SAS': '345678901',
    'Nacre Digital SAS': '456789012',
    'Boréal IT SAS': '567890123',
    'Plume Communication SAS': '678901234',
    'Quartz Data SAS': '789012345',
    'Horizon Formation SAS': '890123456',
    'Élan Marketing SAS': '901234567',
    'Rivage Ingénierie SAS': '912345678',
}


def company_profiles(invoices):
    """Include existing suppliers so records remain reachable after the UI update."""
    profiles = DEMO_SMES.copy()
    for invoice in invoices:
        profiles[invoice['seller']] = invoice['siren']
    return profiles


def sme_invoices(invoices, company):
    if company == ALL_SMES:
        return list(invoices)
    return [i for i in invoices if canonical(i['seller']) == canonical(company)] if company else []


def apply_sme_profile(state, company, profiles):
    """Drop another company's invoice draft before any upload widgets are built."""
    if state.get('sme_active_profile', ALL_SMES) == company:
        return
    keys = ('ui_sme_name', 'ui_siren_9_digit_format', 'ui_buyer', 'ui_buyer_email',
            'ui_invoice_reference', 'ui_invoice_amount', 'ui_issue_date', 'ui_due_date',
            'ui_original_invoice_pdf_png_or_jpeg_10_mb_max', 'invoice_prefill_digest',
            'invoice_prefill', 'focus_invoice')
    for key in keys:
        state.pop(key, None)
    if company != ALL_SMES and company in profiles:
        state['ui_sme_name'] = company
        state['ui_siren_9_digit_format'] = profiles[company]
    state['sme_active_profile'] = company


def validate_sme_submission(company, seller):
    if company != ALL_SMES and canonical(seller) != canonical(company):
        raise ValueError('The supplier on this invoice differs from the selected SME profile. Select the matching company or the all-companies view.')
