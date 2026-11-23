"""Confirmation-link security, lifecycle and mail drafts, without network calls."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit
from buyer_confirmation import (ConfirmationError, create_invitation, email_draft,
                                inspect_invitation, public_url, respond, validate_email)
from engine import eligible, new_invoice
from storage import InvoiceStore


class ConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = InvoiceStore(Path(self.directory.name)/'invoices.db')
        self.store.initialize([])
        self.invoice = new_invoice([], seller='Supplier', siren='123456789', buyer='Buyer',
            reference='LINK-001', amount=10000, issued=date.today(), due=date.today()+timedelta(days=60),
            documents=True, identity=True, strength='Strong', history='On time')
        self.store.add(self.invoice)
        self.now = datetime(2026, 11, 23, 12, tzinfo=timezone.utc)

    def invitation(self, **kwargs):
        return create_invitation(self.store, self.invoice['id'], 'buyer@example.com',
                                 'https://invoiceflow.streamlit.app/?embed=true#old', now=self.now, **kwargs)

    def test_prepare_does_not_approve_or_store_plaintext_token(self):
        draft = self.invitation()
        invoice = self.store.load()[0]
        self.assertEqual(invoice['buyer_status'], 'Pending')
        self.assertFalse(eligible(invoice))
        self.assertEqual(len(draft['token']), 43)
        self.assertNotIn(draft['token'], json.dumps(invoice))
        self.assertEqual(parse_qs(urlsplit(draft['link']).query), {'confirmation':[draft['token']]})
        self.assertEqual(urlsplit(draft['link']).fragment, '')
        before = deepcopy(invoice)
        self.assertEqual(inspect_invitation(self.store, draft['token'], now=self.now)['id'], invoice['id'])
        self.assertEqual(self.store.load()[0], before)  # link preview/GET is read-only

    def test_confirm_saved_atomically_and_survives_another_session(self):
        draft = self.invitation()
        respond(self.store, draft['token'], approved=True, name='Jane Doe', attestation=True, now=self.now)
        invoice = InvoiceStore(self.store.path).load()[0]
        self.assertTrue(eligible(invoice))
        record = invoice['buyer_confirmation']
        self.assertEqual(record['status'], 'confirmed')
        self.assertEqual(record['respondent_name'], 'Jane Doe')
        self.assertEqual(record['responded_at'], self.now.isoformat())
        self.assertTrue(record['attestation'])
        self.assertEqual(record['method'], 'personal_link')

    def test_dispute_requires_reason_and_blocks_financing(self):
        draft=self.invitation()
        with self.assertRaises(ConfirmationError):
            respond(self.store,draft['token'],approved=False,name='Jane',now=self.now)
        respond(self.store,draft['token'],approved=False,name='Jane',note='Wrong amount',now=self.now)
        invoice=self.store.load()[0]
        self.assertEqual(invoice['buyer_status'],'Disputed')
        self.assertEqual(invoice['note'],'Wrong amount')
        self.assertFalse(eligible(invoice))

    def test_no_confirmation_without_name_and_attestation(self):
        draft=self.invitation()
        for name, attestation in [('',True),('Jane',False)]:
            with self.assertRaises(ConfirmationError):
                respond(self.store,draft['token'],approved=True,name=name,attestation=attestation,now=self.now)
        self.assertFalse(eligible(self.store.load()[0]))

    def test_one_response_cannot_be_replayed_or_overwritten(self):
        draft=self.invitation()
        respond(self.store,draft['token'],approved=True,name='Jane',attestation=True,now=self.now)
        before=self.store.load()[0]
        with self.assertRaises(ConfirmationError):
            respond(self.store,draft['token'],approved=False,name='Other',note='overwrite',now=self.now)
        with self.assertRaises(ConfirmationError):
            self.invitation(replace=True)
        self.assertEqual(self.store.load()[0],before)
        self.assertEqual(inspect_invitation(self.store,draft['token'],now=self.now)['buyer_confirmation']['status'],'confirmed')

    def test_expired_link_rejected_both_on_view_and_submission(self):
        draft=self.invitation()
        later=self.now+timedelta(days=7)
        for action in [lambda: inspect_invitation(self.store,draft['token'],now=later),
                       lambda: respond(self.store,draft['token'],approved=True,name='Jane',attestation=True,now=later)]:
            with self.assertRaisesRegex(ConfirmationError,'expired'):
                action()
        self.assertFalse(eligible(self.store.load()[0]))

    def test_replacement_is_explicit_and_invalidates_old_token(self):
        old=self.invitation()
        with self.assertRaises(ConfirmationError):
            self.invitation()
        new=self.invitation(replace=True)
        self.assertNotEqual(old['token'],new['token'])
        with self.assertRaises(ConfirmationError):
            inspect_invitation(self.store,old['token'],now=self.now)
        inspect_invitation(self.store,new['token'],now=self.now)

    def test_invoice_change_blocks_view_and_response(self):
        draft=self.invitation()
        invoice=self.store.load()[0];invoice['amount']=20000;self.store.update(invoice)
        with self.assertRaisesRegex(ConfirmationError,'changed'):
            inspect_invitation(self.store,draft['token'],now=self.now)
        with self.assertRaisesRegex(ConfirmationError,'changed'):
            respond(self.store,draft['token'],approved=True,name='Jane',attestation=True,now=self.now)

    def test_unknown_malformed_and_deleted_tokens_are_generic_errors(self):
        draft=self.invitation()
        for token in ['',None,'?',draft['token'][:-1], 'x'*43]:
            with self.assertRaisesRegex(ConfirmationError,'invalid or unavailable'):
                inspect_invitation(self.store,token,now=self.now)
        self.store.reset([])
        with self.assertRaises(ConfirmationError):
            inspect_invitation(self.store,draft['token'],now=self.now)

    def test_latest_database_state_and_stale_browser_protection(self):
        old=self.store.load()[0]
        self.invitation()
        with self.assertRaises(ValueError):
            self.store.update(old)
        fresh=self.store.load()[0]
        fresh['status']='Closed';self.store.update(fresh)
        with self.assertRaises(ConfirmationError):
            self.invitation(replace=True)

    def test_wrong_email_and_unsafe_url_never_save_an_attempt(self):
        for email in ['bad','a@b.com\r\nBcc: x@y.com','a,b@example.com','a;b@example.com']:
            with self.assertRaises(ConfirmationError): validate_email(email)
        for url in ['http://public.example.com','javascript:alert(1)','https://user:pass@example.com','']:
            with self.assertRaises(ConfirmationError): public_url(url)
        self.assertEqual(public_url('http://localhost:8501/?confirmation=old'),'http://localhost:8501/')
        self.assertNotIn('buyer_confirmation', self.store.load()[0])

    def test_mailto_uses_single_recipient_and_encoded_subject_and_body(self):
        draft=self.invitation()
        for language in ['FR','EN']:
            mail=email_draft(dict(self.invoice, reference='REF\r\nBcc:evil'),draft,language)
            uri=urlsplit(mail['mailto']);fields=parse_qs(uri.query)
            self.assertEqual(uri.scheme,'mailto')
            self.assertEqual(uri.path,'buyer@example.com')
            self.assertEqual(set(fields),{'subject','body'})
            self.assertNotIn('\n',fields['subject'][0])
            self.assertIn(draft['link'],fields['body'][0])
            self.assertIn('10000.00',mail['body'])


if __name__=='__main__': unittest.main()
