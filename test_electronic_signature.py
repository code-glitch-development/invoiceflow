"""Contract and persistence tests; never send mail or call a real signature service."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError, URLError
from datetime import date, timedelta
from electronic_signature import (SignatureError, YousignClient, confirmation_pdf,
    download_evidence, refresh_signature, send_signature, validate_email)
from engine import new_invoice, eligible
from storage import InvoiceStore


CONTACT = dict(email='buyer@example.com', first_name='Jane', last_name='Doe')


class SignatureTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = InvoiceStore(Path(self.directory.name) / 'invoices.db')
        self.store.initialize([])
        self.invoice = new_invoice([], seller='Supplier & Co', siren='123456789', buyer='Buyer Inc',
            reference='INV-001', amount=10000, issued=date.today(), due=date.today()+timedelta(days=60),
            documents=True, identity=True, strength='Strong', history='On time')
        self.store.add(self.invoice)
        self.client = Mock(environment='sandbox')
        self.client.request.side_effect = [{'id': 'request'}, {'id': 'document'},
                                           {'id': 'signer'}, {'status': 'ongoing'}]

    def sent(self):
        send_signature(self.store, self.invoice['id'], self.client, CONTACT)
        return self.store.load()[0]

    def remote(self, state='done', signer='signer', signed='signed'):
        self.client.request.side_effect = None
        self.client.request.return_value = dict(id='request', status=state,
            signers=[dict(id=signer, status=signed)], completed_at='2026-11-23T12:00:00Z')

    def test_send_delegates_email_to_provider_and_keeps_invoice_pending(self):
        invoice = self.sent()
        record = invoice['signature']
        self.assertEqual(record['state'], 'ongoing')
        self.assertEqual(invoice['buyer_status'], 'Pending')
        self.assertFalse(eligible(invoice))
        self.assertNotIn('signature_link', json.dumps(record))
        calls = self.client.request.call_args_list
        self.assertEqual(calls[0].args[2]['delivery_mode'], 'email')
        self.assertTrue(calls[0].args[2]['signers_allowed_to_decline'])
        self.assertEqual(calls[2].args[2]['signature_authentication_mode'], 'otp_email')
        self.assertEqual(calls[2].args[2]['signature_level'], 'electronic_signature')
        self.assertEqual(calls[2].args[2]['info']['email'], CONTACT['email'])
        self.assertEqual(calls[3].args[:2], ('POST', '/signature_requests/request/activate'))

    def test_only_verified_done_and_expected_signer_confirms_and_survives_reopening(self):
        self.sent()
        self.remote()
        refresh_signature(self.store, self.invoice['id'], self.client)
        actual = InvoiceStore(self.store.path).load()[0]
        self.assertTrue(eligible(actual))
        self.assertEqual(actual['signature']['state'], 'done')
        self.assertEqual(actual['signature']['environment'], 'sandbox')

    def test_pending_expired_and_canceled_never_confirm(self):
        self.sent()
        for state in ('ongoing', 'expired', 'canceled', 'draft'):
            self.remote(state)
            refresh_signature(self.store, self.invoice['id'], self.client)
            self.assertEqual(self.store.load()[0]['buyer_status'], 'Pending')

    def test_wrong_or_unsigned_signer_cannot_confirm(self):
        self.sent()
        for signer, status in [('other', 'signed'), ('signer', 'notified')]:
            self.remote(signer=signer, signed=status)
            with self.assertRaises(SignatureError):
                refresh_signature(self.store, self.invoice['id'], self.client)
            self.assertFalse(eligible(self.store.load()[0]))

    def test_decline_blocks_financing(self):
        self.sent()
        self.remote('declined')
        refresh_signature(self.store, self.invoice['id'], self.client)
        actual = self.store.load()[0]
        self.assertEqual(actual['buyer_status'], 'Disputed')
        self.assertFalse(eligible(actual))

    def test_changed_invoice_cannot_be_confirmed(self):
        self.sent()
        invoice = self.store.load()[0]
        invoice['amount'] = 20000
        self.store.update(invoice)
        self.remote()
        with self.assertRaisesRegex(SignatureError, 'invoice changed'):
            refresh_signature(self.store, self.invoice['id'], self.client)
        self.assertFalse(eligible(self.store.load()[0]))

    def test_no_second_invitation_even_after_activation_timeout(self):
        self.client.request.side_effect = [{'id':'request'}, {'id':'document'},
                                           {'id':'signer'}, SignatureError('timeout')]
        with self.assertRaises(SignatureError):
            send_signature(self.store, self.invoice['id'], self.client, CONTACT)
        actual = self.store.load()[0]
        self.assertEqual(actual['signature']['state'], 'needs_review')
        calls = self.client.request.call_count
        with self.assertRaisesRegex(SignatureError, 'already exists'):
            send_signature(self.store, self.invoice['id'], self.client, CONTACT)
        self.assertEqual(self.client.request.call_count, calls)
        # If activation did succeed remotely, a fresh API read recovers it safely.
        self.remote()
        refresh_signature(self.store, self.invoice['id'], self.client)
        self.assertTrue(eligible(self.store.load()[0]))

    def test_create_timeout_preserves_unknown_attempt_without_false_confirmation(self):
        self.client.request.side_effect = SignatureError('timeout')
        with self.assertRaises(SignatureError):
            send_signature(self.store, self.invoice['id'], self.client, CONTACT)
        self.assertEqual(self.store.load()[0]['signature']['state'], 'needs_review')
        with self.assertRaisesRegex(SignatureError, 'No remote'):
            refresh_signature(self.store, self.invoice['id'], self.client)
        self.assertEqual(self.store.load()[0]['buyer_status'], 'Pending')

    def test_duplicate_send_rejected_and_old_browser_version_cannot_overwrite_signature(self):
        old = self.store.load()[0]
        self.sent()
        with self.assertRaises(ValueError):
            self.store.update(old)
        with self.assertRaises(SignatureError):
            send_signature(self.store, self.invoice['id'], self.client, CONTACT)

    def test_invalid_contacts_do_not_create_attempt_or_call_api(self):
        for contact in [dict(CONTACT, email='bad'), dict(CONTACT, email='a@b.com\r\nBcc: x@y.com'),
                        dict(CONTACT, first_name='')]:
            with self.assertRaises(SignatureError):
                send_signature(self.store, self.invoice['id'], self.client, contact)
        self.assertNotIn('signature', self.store.load()[0])
        self.client.request.assert_not_called()

    def test_environment_cannot_be_switched_for_an_existing_request(self):
        self.sent()
        self.client.environment = 'production'
        with self.assertRaises(SignatureError):
            refresh_signature(self.store, self.invoice['id'], self.client)

    def test_evidence_only_after_provider_completion(self):
        invoice = self.sent()
        with self.assertRaises(SignatureError):
            download_evidence(invoice, self.client)
        self.remote()
        refresh_signature(self.store, self.invoice['id'], self.client)
        invoice = self.store.load()[0]
        self.client.request.return_value = b'%PDF-proof'
        self.assertEqual(download_evidence(invoice, self.client), b'%PDF-proof')
        self.assertEqual(self.client.request.call_args.args[1],
                         '/signature_requests/request/documents/document/download')
        download_evidence(invoice, self.client, audit=True)
        self.assertEqual(self.client.request.call_args.args[1], '/signature_requests/request/audit_trails/download')

    def test_pdf_contains_exact_terms_and_original_hash_without_html_injection(self):
        from pypdf import PdfReader
        invoice = dict(self.invoice, file_hash='a'*64, seller='<b>Supplier</b>')
        raw = confirmation_pdf(invoice, CONTACT, 'sandbox')
        reader = PdfReader(BytesIO(raw))
        text = '\n'.join(p.extract_text() for p in reader.pages)
        self.assertIn('10000.00 EUR', text)
        self.assertIn(invoice['due'], text)
        self.assertIn('ENVIRONNEMENT DE TEST', text)
        self.assertIn('<b>Supplier</b>', text)
        self.assertIn('a'*64, text)
        self.assertEqual(len(reader.pages), 1)
        self.assertEqual(validate_email(' buyer@example.com '), CONTACT['email'])


class TransportTests(unittest.TestCase):
    def test_auth_and_multipart_and_explicit_production(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"id":"document"}'
        opener = Mock(return_value=response)
        client = YousignClient('private-key', 'production', opener=opener)
        client.request('POST', '/signature_requests/id/documents', pdf=b'%PDF-demo')
        request = opener.call_args.args[0]
        self.assertTrue(request.full_url.startswith('https://api.yousign.app/v3/'))
        self.assertEqual(request.get_header('Authorization'), 'Bearer private-key')
        self.assertIn(b'name="nature"', request.data)
        self.assertIn(b'%PDF-demo', request.data)
        self.assertEqual(opener.call_args.kwargs['timeout'], 25)

    def test_network_and_http_errors_do_not_expose_secrets_or_personal_data(self):
        errors = [URLError('private-key buyer@example.com'),
                  HTTPError('https://example.com', 401, 'private-key', {}, None)]
        for error in errors:
            client = YousignClient('private-key', opener=Mock(side_effect=error))
            with self.assertRaises(SignatureError) as caught:
                client.request('GET', '/signature_requests/id')
            self.assertNotIn('private-key', str(caught.exception))
            self.assertNotIn('buyer@example.com', str(caught.exception))
        with self.assertRaises(SignatureError):
            YousignClient('secret', 'arbitrary-host')
        with self.assertRaises(SignatureError):
            YousignClient('')


if __name__ == '__main__':
    unittest.main()
