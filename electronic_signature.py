"""Yousign API v3 integration. Only server-to-server status can confirm an invoice."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
import re
import secrets
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4
from xml.sax.saxutils import escape


class SignatureError(ValueError):
    pass


def validate_email(value):
    value = value.strip()
    if len(value) > 254 or not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", value):
        raise SignatureError('Enter a valid buyer email address.')
    return value


def snapshot(invoice):
    fields = ('id', 'seller', 'siren', 'buyer', 'reference', 'amount', 'issued', 'due', 'file_hash')
    return {key: invoice.get(key) for key in fields}


def fingerprint(invoice):
    return sha256(json.dumps(snapshot(invoice), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def confirmation_pdf(invoice, contact, environment):
    """A separate, explicit confirmation attestation; never pretend to sign an absent original."""
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    output = BytesIO()
    styles = getSampleStyleSheet()
    content = []
    lines = [
        ('InvoiceFlow - Confirmation de facture', 'Title'),
        ('ENVIRONNEMENT DE TEST - AUCUN FINANCEMENT REEL' if environment == 'sandbox'
         else 'Attestation de confirmation par l’acheteur', 'Heading2'),
        ('Ce document est une attestation distincte de la facture originale.', 'Normal'),
    ]
    for label, value in [('Prestataire', invoice['seller']), ('SIREN du prestataire', invoice['siren']),
                         ('Acheteur', invoice['buyer']), ('Reference', invoice['reference']),
                         ('Montant TTC', f"{invoice['amount']:.2f} EUR"),
                         ('Date de facture', invoice['issued']), ('Echeance', invoice['due']),
                         ('Signataire', f"{contact['first_name']} {contact['last_name']}"),
                         ('Email', contact['email'])]:
        lines.append((f'{label} : {value}', 'Normal'))
    lines += [
        ('Je declare etre habilite a representer l’acheteur indique ci-dessus. Je confirme la prestation '
         'ou livraison correspondant a cette facture, son montant et son echeance. A la date de signature, '
         'je declare la facture non payee et non contestee.', 'Normal'),
        ('Cette confirmation ne constitue ni une cession de creance ni une garantie de paiement.', 'Normal'),
        ('Empreinte du dossier : ' + fingerprint(invoice), 'Code'),
    ]
    if invoice.get('file_hash'):
        lines.append(('SHA-256 du fichier original depose : ' + invoice['file_hash'], 'Code'))
    for text, style in lines:
        content.extend([Paragraph(escape(text), styles[style]), Spacer(1, 9)])
    # Fixed footer leaves a clear, predictable field on page 1, independent of body flow.
    def footer(canvas, doc):
        canvas.setStrokeColor(colors.HexColor('#00a58c'))
        canvas.rect(45, 50, 230, 75)
        canvas.setFont('Helvetica', 9)
        canvas.drawString(50, 135, 'Signature du representant de l’acheteur')
    SimpleDocTemplate(output, pagesize=(595, 842), topMargin=35, bottomMargin=165,
                      leftMargin=45, rightMargin=45).build(content, onFirstPage=footer)
    return output.getvalue()


class YousignClient:
    def __init__(self, api_key, environment='sandbox', opener=urlopen):
        if environment not in ('sandbox', 'production'):
            raise SignatureError('Invalid signature service environment.')
        if not api_key.strip():
            raise SignatureError('The electronic signature service is not configured.')
        self.api_key, self.environment, self.opener = api_key, environment, opener
        self.base = ('https://api-sandbox.yousign.app/v3' if environment == 'sandbox'
                     else 'https://api.yousign.app/v3')

    def request(self, method, path, payload=None, pdf=None, binary=False):
        headers = {'Authorization': 'Bearer ' + self.api_key,
                   'Accept': '*/*' if binary else 'application/json'}
        data = None
        if pdf is not None:
            boundary = uuid4().hex
            headers['Content-Type'] = 'multipart/form-data; boundary=' + boundary
            data = (f'--{boundary}\r\nContent-Disposition: form-data; name="nature"\r\n\r\nsignable_document\r\n'
                    f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="confirmation.pdf"\r\n'
                    'Content-Type: application/pdf\r\n\r\n').encode() + pdf + f'\r\n--{boundary}--\r\n'.encode()
        elif payload is not None:
            data = json.dumps(payload).encode()
            headers['Content-Type'] = 'application/json'
        elif method == 'POST':
            data = b''
        try:
            with self.opener(Request(self.base + path, data=data, headers=headers, method=method), timeout=25) as response:
                result = response.read(20 * 1024 * 1024 + 1)
            if len(result) > 20 * 1024 * 1024:
                raise SignatureError('The signature service returned an oversized response.')
            return result if binary else json.loads(result)
        except HTTPError as exc:
            # Do not expose API responses containing personal data or authentication details.
            raise SignatureError('The signature service rejected the request. Check its configuration and dashboard.') from exc
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            raise SignatureError('Signature service unavailable. Check its dashboard before retrying an uncertain send.') from exc


def _edit(store, invoice_id, operation):
    """Short transactions; no network calls while the database lock is held."""
    with store.transaction() as db:
        row = db.execute('SELECT payload FROM invoices WHERE id = ?', (invoice_id,)).fetchone()
        if row is None:
            raise SignatureError('Invoice not found.')
        invoice = json.loads(row[0])
        operation(invoice)
        db.execute('UPDATE invoices SET payload = ?, version = version + 1 WHERE id = ?',
                   (store.payload(invoice), invoice_id))
    return invoice


def send_signature(store, invoice_id, client, contact):
    contact = {key: str(contact.get(key, '')).strip() for key in ('first_name', 'last_name', 'email')}
    contact['email'] = validate_email(contact['email'])
    if any(not contact[k] or len(contact[k]) > 80 for k in ('first_name', 'last_name')):
        raise SignatureError('Enter the signer first and last names (80 characters maximum).')
    attempt = secrets.token_hex(16)

    def reserve(invoice):
        if invoice.get('financing') or invoice['status'] in ('Financed', 'Closed'):
            raise SignatureError('A financed or closed invoice cannot be changed.')
        if invoice.get('signature'):
            raise SignatureError('A signature request already exists. Refresh its status instead of sending again.')
        if invoice['buyer_status'] == 'Confirmed':
            raise SignatureError('This invoice is already confirmed.')
        invoice['buyer_email'] = contact['email']
        invoice['signature'] = dict(attempt=attempt, provider='yousign', environment=client.environment,
            state='creating', contact=contact, snapshot_hash=fingerprint(invoice),
            created_at=datetime.now(timezone.utc).isoformat())

    invoice = _edit(store, invoice_id, reserve)
    record = invoice['signature']

    def save(**values):
        def update(current):
            if current.get('signature', {}).get('attempt') != attempt:
                raise SignatureError('The signature request changed. Reload the invoice.')
            current['signature'].update(values)
        _edit(store, invoice_id, update)
        record.update(values)

    try:
        request = client.request('POST', '/signature_requests', {
            'name': ('InvoiceFlow - ' + invoice['reference'])[:100],
            'delivery_mode': 'email', 'external_id': invoice_id + '-' + attempt,
            'signers_allowed_to_decline': True, 'audit_trail_locale': 'fr'})
        save(request_id=request['id'], state='draft')
        path = '/signature_requests/' + request['id']
        document_bytes = confirmation_pdf(invoice, contact, client.environment)
        document = client.request('POST', path + '/documents', pdf=document_bytes)
        save(document_id=document['id'], document_sha256=sha256(document_bytes).hexdigest())
        signer = client.request('POST', path + '/signers', {
            'info': {**contact, 'locale': 'fr'},
            'signature_level': 'electronic_signature', 'signature_authentication_mode': 'otp_email',
            'fields': [{'type': 'signature', 'document_id': document['id'], 'page': 1,
                        'x': 50, 'y': 725, 'width': 220, 'height': 60}]})
        save(signer_id=signer['id'])
        client.request('POST', path + '/activate')
        save(state='ongoing', sent_at=datetime.now(timezone.utc).isoformat(),
             signature_level='electronic_signature', authentication='otp_email')
    except (SignatureError, KeyError, TypeError) as exc:
        save(state='needs_review')
        if isinstance(exc, SignatureError):
            raise
        raise SignatureError('Unexpected signature service response. Check its dashboard before retrying.') from exc


def refresh_signature(store, invoice_id, client):
    invoice = next((i for i in store.load() if i['id'] == invoice_id), None)
    if not invoice:
        raise SignatureError('Invoice not found.')
    record = deepcopy(invoice.get('signature', {}))
    if not record.get('request_id'):
        raise SignatureError('No remote request identifier. Check the signature service dashboard.')
    if record['environment'] != client.environment:
        raise SignatureError('Restore the original signature service environment to access this request.')
    remote = client.request('GET', '/signature_requests/' + record['request_id'])
    state = remote.get('status')
    if remote.get('id') != record['request_id'] or not isinstance(state, str):
        raise SignatureError('Unexpected signature service response. Check its dashboard before retrying.')
    # A redirect, uploaded PDF or user checkbox can never substitute for provider verification.
    signers = remote.get('signers', [])
    complete = (state == 'done' and len(signers) == 1 and
                signers[0].get('id') == record.get('signer_id') and signers[0].get('status') == 'signed')
    if state == 'done' and not complete:
        raise SignatureError('The expected signer has not been verified as signed.')

    def apply(current):
        saved = current.get('signature', {})
        if saved.get('attempt') != record['attempt'] or fingerprint(current) != record['snapshot_hash']:
            raise SignatureError('The invoice changed after the signature request. Confirmation is blocked.')
        saved.update(state=state, checked_at=datetime.now(timezone.utc).isoformat())
        if complete:
            from engine import confirm
            if not current.get('financing') and current['status'] != 'Closed':
                confirm(current, True)
            saved['completed_at'] = remote.get('completed_at') or saved['checked_at']
        elif state == 'declined' and not current.get('financing') and current['status'] != 'Closed':
            from engine import confirm
            confirm(current, False, 'The buyer declined the electronic signature request.')
    _edit(store, invoice_id, apply)
    return state


def download_evidence(invoice, client, audit=False):
    record = invoice.get('signature', {})
    if record.get('state') != 'done' or record.get('environment') != client.environment:
        raise SignatureError('Signed evidence is unavailable.')
    path = '/signature_requests/' + record['request_id']
    if audit:
        return client.request('GET', path + '/audit_trails/download', binary=True)
    return client.request('GET', path + '/documents/' + record['document_id'] + '/download', binary=True)
