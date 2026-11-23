"""Brevo HTTPS mail transport and persisted send attempts. No SMTP/SDK dependency."""
from datetime import datetime, timezone
import hmac
import json
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4
from buyer_confirmation import (ConfirmationError, _record, _check, email_draft,
                                validate_email)


class MailError(ValueError):
    def __init__(self, message, uncertain=False):
        super().__init__(message)
        self.uncertain = uncertain


def authorise_send(entered_code, expected_code):
    if len(expected_code) < 12 or not hmac.compare_digest(entered_code.encode(), expected_code.encode()):
        raise MailError('Enter the correct mail sending access code.')


class BrevoClient:
    def __init__(self, api_key, sender_email, sender_name='InvoiceFlow', opener=urlopen):
        if not api_key.strip():
            raise MailError('Automatic email is not configured.')
        self.api_key = api_key
        self.sender_email = validate_email(sender_email)
        self.sender_name = sender_name.strip()[:80] or 'InvoiceFlow'
        self.opener = opener

    def send(self, recipient, message, attempt):
        payload = {'sender': {'email': self.sender_email, 'name': self.sender_name},
                   'to': [{'email': validate_email(recipient)}],
                   'subject': message['subject'], 'textContent': message['body'],
                   'tags': ['invoiceflow-confirmation', attempt]}
        request = Request('https://api.brevo.com/v3/smtp/email',
                          data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                          headers={'api-key': self.api_key, 'Content-Type': 'application/json',
                                   'Accept': 'application/json'}, method='POST')
        try:
            with self.opener(request, timeout=20) as response:
                raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError('oversized response')
            result = json.loads(raw)
            if not isinstance(result, dict) or not isinstance(result.get('messageId'), str) or not result['messageId']:
                raise ValueError('missing message identifier')
            return result['messageId']
        except HTTPError as exc:
            if 400 <= exc.code < 500 and exc.code != 408:
                if exc.code in (401, 403):
                    raise MailError('The mail service rejected access. Check the API key, sender and account activation.') from exc
                if exc.code == 429:
                    raise MailError('The mail service limit was reached. Check your Brevo account and try later.') from exc
                raise MailError('The mail service refused the email. Check the sender, recipient and Brevo logs.') from exc
            raise MailError('Email sending is uncertain. Check Brevo transactional logs before any new send.', uncertain=True) from exc
        except (URLError, OSError, ValueError) as exc:
            # A timeout/malformed success can occur after acceptance: never retry automatically.
            raise MailError('Email sending is uncertain. Check Brevo transactional logs before any new send.', uncertain=True) from exc


def send_confirmation_email(store, invoice_id, invitation, client, *, entered_code,
                            expected_code, language='FR', now=None):
    authorise_send(entered_code, expected_code)
    moment = now or datetime.now(timezone.utc)
    attempt = uuid4().hex
    token = invitation['token']
    if parse_qs(urlsplit(invitation['link']).query) != {'confirmation': [token]}:
        raise MailError('The email link does not match this confirmation request.')
    with store.transaction() as db:
        identifier, invoice, record = _record(db, token)
        _check(invoice, record, moment)
        if identifier != invoice_id or record['email'] != invitation['email'] or record['status'] != 'pending':
            raise MailError('The confirmation request changed. Reload the invoice.')
        prior = record.get('email_delivery', {})
        if prior.get('state') in ('sending', 'accepted', 'unknown'):
            raise MailError('This email has already been submitted or its sending is uncertain. Check the mail status first.')
        record['email_delivery'] = dict(state='sending', attempt=attempt, provider='brevo',
                                       attempted_at=moment.isoformat())
        db.execute('UPDATE invoices SET payload = ?, version = version + 1 WHERE id = ?',
                   (store.payload(invoice), identifier))
    message = email_draft(invoice, invitation, language)

    def save(state, **values):
        with store.transaction() as db:
            row = db.execute('SELECT payload FROM invoices WHERE id = ?', (invoice_id,)).fetchone()
            if row is None:
                raise MailError('The email attempt could not be saved. Check Brevo logs before sending again.', uncertain=True)
            current = json.loads(row[0])
            saved_record = current.get('buyer_confirmation', {})
            delivery = saved_record.get('email_delivery', {})
            if saved_record.get('token_hash') != record['token_hash'] or delivery.get('attempt') != attempt:
                raise MailError('The email attempt could not be saved. Check Brevo logs before sending again.', uncertain=True)
            delivery.update(state=state, **values)
            # Merge only delivery fields: preserve a buyer response submitted during the API call.
            db.execute('UPDATE invoices SET payload = ?, version = version + 1 WHERE id = ?',
                       (store.payload(current), invoice_id))
    try:
        identifier = client.send(record['email'], message, attempt)
    except MailError as exc:
        save('unknown' if exc.uncertain else 'rejected')
        raise
    save('accepted', message_id=identifier, accepted_at=datetime.now(timezone.utc).isoformat())
    return identifier
