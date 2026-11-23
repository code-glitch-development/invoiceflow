"""Single-use buyer confirmation links. No email service, external API or signing claim."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
import json
import re
import secrets
from urllib.parse import quote, urlencode, urlsplit, urlunsplit


class ConfirmationError(ValueError):
    pass


def validate_email(value):
    value = value.strip()
    if len(value) > 254 or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", value):
        raise ConfirmationError('Enter a valid buyer email address.')
    return value


def invoice_fingerprint(invoice):
    fields = ('id', 'seller', 'siren', 'buyer', 'reference', 'amount', 'issued', 'due', 'file_hash')
    payload = {field: invoice.get(field) for field in fields}
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def public_url(value):
    try:
        parts = urlsplit(value.strip())
        local = parts.hostname in ('localhost', '127.0.0.1', '::1')
        if (not parts.hostname or parts.username or parts.password or
                (parts.scheme != 'https' and not (parts.scheme == 'http' and local))):
            raise ValueError()
        # Never carry a previous recipient token, tracking parameter or URL fragment.
        return urlunsplit((parts.scheme, parts.netloc, parts.path or '/', '', ''))
    except ValueError as exc:
        raise ConfirmationError('Enter the public HTTPS address of this InvoiceFlow app.') from exc


def _now(value=None):
    return value or datetime.now(timezone.utc)


def _digest(token):
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        raise ConfirmationError('This confirmation link is invalid or unavailable.')
    return sha256(token.encode()).hexdigest()


def _record(db, token):
    digest = _digest(token)
    for identifier, payload in db.execute('SELECT id, payload FROM invoices').fetchall():
        invoice = json.loads(payload)
        record = invoice.get('buyer_confirmation', {})
        if record.get('token_hash') and hmac.compare_digest(record['token_hash'], digest):
            return identifier, invoice, record
    raise ConfirmationError('This confirmation link is invalid or unavailable.')


def _check(invoice, record, now):
    # An already submitted response is a receipt; replay can never change the decision.
    if record['status'] != 'pending':
        return
    if datetime.fromisoformat(record['expires_at']) <= now:
        raise ConfirmationError('This confirmation link has expired. Ask the supplier for a new link.')
    if record['invoice_hash'] != invoice_fingerprint(invoice):
        raise ConfirmationError('The invoice changed after this link was created. Ask for a new link.')
    if invoice.get('financing') or invoice['status'] in ('Financed', 'Closed') or invoice['buyer_status'] == 'Confirmed':
        raise ConfirmationError('This invoice can no longer receive a confirmation through this link.')


def create_invitation(store, invoice_id, email, app_url, *, replace=False, now=None):
    email, base = validate_email(email), public_url(app_url)
    token = secrets.token_urlsafe(32)
    moment = _now(now)
    with store.transaction() as db:
        row = db.execute('SELECT payload FROM invoices WHERE id = ?', (invoice_id,)).fetchone()
        if row is None:
            raise ConfirmationError('Invoice not found.')
        invoice = json.loads(row[0])
        if invoice.get('financing') or invoice['status'] in ('Financed', 'Closed') or invoice['buyer_status'] == 'Confirmed':
            raise ConfirmationError('A confirmed, financed or closed invoice cannot receive a new link.')
        old = invoice.get('buyer_confirmation')
        if old and old['status'] != 'pending':
            raise ConfirmationError('The buyer has already responded. Their decision cannot be overwritten.')
        if old and not replace:
            raise ConfirmationError('A link already exists. Explicitly replace it to invalidate the previous link.')
        record = dict(status='pending', email=email, token_hash=sha256(token.encode()).hexdigest(),
                      invoice_hash=invoice_fingerprint(invoice), created_at=moment.isoformat(),
                      expires_at=(moment + timedelta(days=7)).isoformat(), method='personal_link')
        invoice.update(buyer_email=email, buyer_confirmation=record)
        db.execute('UPDATE invoices SET payload = ?, version = version + 1 WHERE id = ?',
                   (store.payload(invoice), invoice_id))
    return dict(token=token, link=base + '?' + urlencode({'confirmation': token}),
                token_hash=record['token_hash'], expires_at=record['expires_at'], email=email)


def inspect_invitation(store, token, *, now=None):
    with store.transaction() as db:
        _, invoice, record = _record(db, token)
        _check(invoice, record, _now(now))
    # Only the single referenced invoice reaches the recipient UI, never the shared list.
    return invoice


def respond(store, token, *, approved, name, attestation=False, note='', now=None):
    name, note = name.strip(), note.strip()
    if not name or len(name) > 160:
        raise ConfirmationError('Enter your full name (160 characters maximum).')
    if not isinstance(approved, bool):
        raise ConfirmationError('Choose a confirmation decision.')
    if approved and not attestation:
        raise ConfirmationError('Check the declaration before confirming this invoice.')
    if not approved and not note:
        raise ConfirmationError('Provide a reason for the dispute.')
    if len(note) > 2000:
        raise ConfirmationError('The comment must contain at most 2000 characters.')
    moment = _now(now)
    with store.transaction() as db:
        identifier, invoice, record = _record(db, token)
        _check(invoice, record, moment)
        if record['status'] != 'pending':
            raise ConfirmationError('The buyer has already responded. Their decision cannot be overwritten.')
        from engine import confirm
        confirm(invoice, approved, note)
        record.update(status='confirmed' if approved else 'disputed', responded_at=moment.isoformat(),
                      respondent_name=name, attestation=bool(attestation) if approved else False, note=note)
        db.execute('UPDATE invoices SET payload = ?, version = version + 1 WHERE id = ?',
                   (store.payload(invoice), identifier))
    return record['status']


def email_draft(invoice, invitation, language='FR'):
    # Single recipient and percent-encoded query parameters avoid mail-header injection.
    reference = ' '.join(invoice['reference'].split())
    if language == 'FR':
        subject = 'Confirmation de facture - ' + reference
        body = (f"Bonjour,\n\n{invoice['seller']} vous invite à vérifier la facture {reference} "
                f"de {invoice['amount']:.2f} EUR, à échéance du {invoice['due']}.\n\n"
                "Consultez ses informations et confirmez-la ou signalez un problème via ce lien personnel :\n"
                f"{invitation['link']}\n\n"
                "Aucun compte ni logiciel à installer. Ce lien permet une seule réponse et expire dans 7 jours. "
                "Ne le transférez pas. Il s’agit d’une confirmation par lien, pas d’une signature électronique certifiée.\n\n"
                "Merci.")
    else:
        subject = 'Invoice confirmation - ' + reference
        body = (f"Hello,\n\n{invoice['seller']} invites you to review invoice {reference} "
                f"for EUR {invoice['amount']:.2f}, due {invoice['due']}.\n\n"
                "Review the details and confirm or report a problem using this personal link:\n"
                f"{invitation['link']}\n\n"
                "No account or installation is needed. The link allows one response and expires in 7 days. "
                "Do not forward it. This is confirmation by link, not a certified electronic signature.\n\nThank you.")
    mailto = 'mailto:' + quote(invitation['email'], safe='@') + '?' + urlencode(
        {'subject': subject, 'body': body}, quote_via=quote)
    return dict(subject=subject, body=body, mailto=mailto)

