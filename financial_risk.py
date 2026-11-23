"""Published Altman Z-double-prime indicator, without a score-to-PD/rate mapping."""
from datetime import date, datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
import math
import re
from future_value import valuation_today

MODEL = 'Altman Z-double-prime, no emerging-market intercept'
SOURCE = 'https://doi.org/10.3390/risks6040117'
REFERENCE = 'https://archive.nyu.edu/jspui/bitstream/2451/26400/2/FIN-05-001.pdf'
FIELDS = {
    'total_assets': 'Total assets (€)',
    'current_assets': 'Current assets, including cash (€)',
    'current_liabilities': 'Current liabilities due within one year (€)',
    'total_liabilities': 'Total non-equity liabilities (€)',
    'equity': 'Book value of equity (€)',
    'retained_earnings': 'Accumulated retained earnings / losses (€)',
    'ebit': 'Earnings before interest and tax — EBIT (€)',
}
MAX_AGE_DAYS = 548  # V1 freshness policy, not an Altman statistical threshold.
COEFFICIENTS = {'X1': 6.56, 'X2': 3.26, 'X3': 6.72, 'X4': 1.05}


def _canonical(value):
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value)).casefold() if c.isalnum())


def validate_accounts(accounts, buyer, today=None):
    today = today or valuation_today()
    if not accounts:
        raise ValueError('Buyer financial statements have not been provided.')
    if _canonical(accounts.get('entity_name', '')) != _canonical(buyer):
        raise ValueError('The accounts must identify the invoice buyer, not the supplier.')
    if not re.fullmatch(r'\d{9}', accounts.get('buyer_siren', '')):
        raise ValueError('Enter the buyer SIREN (9-digit format only).')
    if accounts.get('company_type') != 'non_financial_non_manufacturing':
        raise ValueError('This model is restricted to non-financial, non-manufacturing companies. No score is assigned outside its scope.')
    try:
        start = date.fromisoformat(accounts['period_start'])
        end = date.fromisoformat(accounts['period_end'])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('Enter valid financial year start and end dates.') from exc
    if not 365 <= (end-start).days+1 <= 366 or end > today:
        raise ValueError('Provide a complete annual accounting period of 365 or 366 days ending no later than today.')
    if (today-end).days > MAX_AGE_DAYS:
        raise ValueError('The accounts are too old for the V1 policy (548 days). Provide more recent annual accounts.')
    from accounting_dates import latest_accounts_check
    check=latest_accounts_check(end,today)
    if check['status']=='obsolete':
        raise ValueError('These accounts are older than the expected latest annual period. Provide newer accounts or request manual review; age alone does not establish fraud.')
    if accounts.get('extraction'):
        extracted_end=accounts['extraction'].get('fields',{}).get('period_end')
        if extracted_end and extracted_end!=end.isoformat():
            raise ValueError('The entered closing date differs from the date detected in the PDF. Correct the document or request manual review.')
        extracted_name=accounts['extraction'].get('fields',{}).get('entity_name')
        if extracted_name and _canonical(extracted_name)!=_canonical(accounts['entity_name']):
            raise ValueError('The entered company name differs from the company detected in the PDF. Request manual review.')
        extracted_siren=accounts['extraction'].get('fields',{}).get('buyer_siren')
        if extracted_siren and extracted_siren!=accounts['buyer_siren']:
            raise ValueError('The entered buyer SIREN differs from the SIREN detected in the PDF.')
        if not accounts.get('extraction_reviewed'):
            raise ValueError('Review the extracted accounting figures against the PDF before saving.')
    if not str(accounts.get('source_reference', '')).strip():
        raise ValueError('Provide the statement source and page references for the entered figures.')
    document = accounts.get('document', {})
    if not document.get('filename') or not re.fullmatch(r'[a-f0-9]{64}', document.get('sha256', '')):
        raise ValueError('Attach the buyer annual statements as a PDF before calculating the indicator.')
    values = accounts.get('values', {})
    for key in FIELDS:
        value = values.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError('Complete every accounting field. Missing values are not replaced with zero.')
    if values['total_assets'] <= 0 or values['total_liabilities'] <= 0:
        raise ValueError('Total assets and total liabilities must be positive for this model.')
    for key in ('current_assets','current_liabilities'):
        if values[key] < 0:
            raise ValueError('Current assets and current liabilities cannot be negative.')
    if values['current_assets'] > values['total_assets'] + 1 or values['current_liabilities'] > values['total_liabilities'] + 1:
        raise ValueError('Current assets/liabilities cannot exceed their corresponding totals.')
    if abs(values['total_assets']-values['equity']-values['total_liabilities']) > 1:
        raise ValueError('The balance sheet does not reconcile: assets must equal equity plus total liabilities (EUR 1 rounding tolerance).')
    return values


def assess_buyer(invoice, today=None):
    accounts = invoice.get('buyer_accounts')
    try:
        v = validate_accounts(accounts, invoice['buyer'], today)
    except ValueError as exc:
        return dict(status='unassessed', value=None, band='Risk not assessed', reason=str(exc), model=MODEL)
    ratios = {'X1': (v['current_assets']-v['current_liabilities'])/v['total_assets'],
              'X2': v['retained_earnings']/v['total_assets'],
              'X3': v['ebit']/v['total_assets'], 'X4': v['equity']/v['total_liabilities']}
    components = {key: COEFFICIENTS[key]*value for key,value in ratios.items()}
    if not all(math.isfinite(number) for number in (*ratios.values(), *components.values())):
        return dict(status='unassessed', value=None, band='Risk not assessed', reason='Accounting ratios exceed the supported numeric range.', model=MODEL)
    value = round(sum(components.values()), 12)
    band = 'Distress zone' if value < 1.1 else 'Grey zone' if value <= 2.6 else 'Lower distress zone'
    return dict(status='assessed', value=value, band=band, ratios=ratios, components=components,
                current_ratio=v['current_assets']/v['current_liabilities'] if v['current_liabilities'] else None,
                equity_ratio_percent=100*v['equity']/v['total_assets'],
                ebit_assets_percent=100*v['ebit']/v['total_assets'],
                model=MODEL, source=SOURCE, reference=REFERENCE, period_end=accounts['period_end'],
                document=accounts['document'], source_reference=accounts['source_reference'])


def prepare_buyer_accounts(invoice, accounts, document_bytes=None, filename=None):
    """Validate annual figures and their source for invoice or company-level storage."""
    from copy import deepcopy
    candidate = deepcopy(accounts)
    if invoice.get('financing') or invoice['status'] == 'Closed':
        raise ValueError('The financial assessment of a financed or closed invoice cannot be changed.')
    if document_bytes is not None:
        if not document_bytes or len(document_bytes) > 5*1024*1024:
            raise ValueError('The annual statements PDF must be non-empty and no larger than 5 MB.')
        try:
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(document_bytes))
            if reader.is_encrypted or not 1 <= len(reader.pages) <= 300:
                raise ValueError()
        except Exception as exc:
            raise ValueError('The annual statements must be a readable, unencrypted PDF (300 pages maximum).') from exc
        candidate['document'] = dict(filename=str(filename or 'annual-accounts.pdf')[:200],
                                     sha256=sha256(document_bytes).hexdigest())
    else:
        candidate['document'] = deepcopy(invoice.get('buyer_accounts', {}).get('document', {}))
    validate_accounts(candidate, invoice['buyer'])
    candidate['entered_at'] = datetime.now(timezone.utc).isoformat()
    candidate['provenance'] = 'Local PDF/OCR-assisted transcription, reviewed by the user; authenticity and identity not independently verified' if candidate.get('extraction') else 'Manual transcription from attached PDF; authenticity and identity not independently verified'
    return candidate


def save_buyer_accounts(store, invoice, accounts, document_bytes=None, filename=None):
    """Archive the PDF and structured entries together, rejecting stale/financed updates."""
    candidate = prepare_buyer_accounts(invoice, accounts, document_bytes, filename)
    with store.transaction() as db:
        row = db.execute('SELECT payload, version FROM invoices WHERE id = ?', (invoice['id'],)).fetchone()
        if row is None or row[1] != invoice.get('_version'):
            raise ValueError('This invoice changed in another session. Reload the latest data before trying again.')
        current = json.loads(row[0])
        if current.get('financing') or current['status'] == 'Closed' or current['buyer'] != invoice['buyer']:
            raise ValueError('The financial assessment of a financed or closed invoice cannot be changed.')
        db.execute('CREATE TABLE IF NOT EXISTS buyer_account_documents (invoice_id TEXT PRIMARY KEY, sha256 TEXT NOT NULL, content BLOB NOT NULL)')
        if document_bytes is not None:
            db.execute('INSERT OR REPLACE INTO buyer_account_documents VALUES (?, ?, ?)',
                       (invoice['id'],candidate['document']['sha256'], document_bytes))
        else:
            stored = db.execute('SELECT sha256 FROM buyer_account_documents WHERE invoice_id = ?', (invoice['id'],)).fetchone()
            if not stored or stored[0] != candidate['document']['sha256']:
                raise ValueError('Attach the buyer annual statements as a PDF before calculating the indicator.')
        current['buyer_accounts'] = candidate
        db.execute('UPDATE invoices SET payload = ?, version = version + 1 WHERE id = ?',
                   (store.payload(current),invoice['id']))


def statement_document(store, invoice):
    with store.transaction() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='buyer_account_documents'").fetchone():
            return None
        row = db.execute('SELECT sha256, content FROM buyer_account_documents WHERE invoice_id = ?', (invoice['id'],)).fetchone()
    if not row or row[0] != invoice.get('buyer_accounts',{}).get('document',{}).get('sha256') or sha256(row[1]).hexdigest() != row[0]:
        return None
    return row[1]
