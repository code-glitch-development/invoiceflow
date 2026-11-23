from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from buyer_confirmation import create_invitation, respond
from buyer_workspace import buyer_invoices, respond_in_workspace
from engine import seed
from storage import InvoiceStore


class BuyerWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = InvoiceStore(Path(self.directory.name)/'buyers.db')
        self.store.initialize(seed())
        self.invoice = self.store.load()[1]
        self.company = self.invoice['buyer']

    def test_filter_matches_only_selected_company(self):
        records = self.store.load()
        selected = buyer_invoices(records, ' groupe horizon ')
        self.assertEqual(len(selected), 2)
        self.assertTrue(all(i['buyer'] == 'Groupe Horizon' for i in selected))
        self.assertEqual(buyer_invoices(records, ''), [])
        self.assertEqual(buyer_invoices(records, 'Unknown'), [])

    def test_confirmation_is_atomic_declared_and_does_not_verify_supplier(self):
        self.invoice.update(identity=False, documents=False)
        self.store.update(self.invoice)
        current = next(i for i in self.store.load() if i['id'] == self.invoice['id'])
        respond_in_workspace(self.store, current, self.company, approved=True, name='Buyer Test', attestation=True)
        saved = next(i for i in self.store.load() if i['id'] == current['id'])
        self.assertEqual(saved['buyer_status'], 'Confirmed')
        self.assertEqual(saved['buyer_confirmation']['method'], 'buyer_workspace_demo')
        self.assertFalse(saved['buyer_confirmation']['identity_verified'])
        self.assertFalse(saved['identity'])
        self.assertFalse(saved['documents'])
        self.assertIsNone(saved['financing'])

    def test_wrong_company_missing_attestation_and_stale_record_rejected(self):
        for args in [dict(company='Another buyer', attestation=True), dict(company=self.company, attestation=False)]:
            with self.assertRaises(ValueError):
                respond_in_workspace(self.store, self.invoice, approved=True, name='Buyer Test', **args)
        self.store.update(deepcopy(self.invoice))
        with self.assertRaises(ValueError):
            respond_in_workspace(self.store, self.invoice, self.company, approved=True, name='Buyer Test', attestation=True)

    def test_dispute_requires_reason_and_cannot_be_overwritten(self):
        with self.assertRaises(ValueError):
            respond_in_workspace(self.store, self.invoice, self.company, approved=False, name='Buyer Test')
        respond_in_workspace(self.store, self.invoice, self.company, approved=False, name='Buyer Test', note='Wrong amount')
        saved = next(i for i in self.store.load() if i['id'] == self.invoice['id'])
        self.assertEqual(saved['buyer_status'], 'Disputed')
        with self.assertRaises(ValueError):
            respond_in_workspace(self.store, saved, self.company, approved=True, name='Another person', attestation=True)

    def test_pending_mail_link_cannot_overwrite_workspace_decision(self):
        invitation = create_invitation(self.store, self.invoice['id'], 'buyer@example.com', 'https://example.com')
        current = next(i for i in self.store.load() if i['id'] == self.invoice['id'])
        respond_in_workspace(self.store, current, self.company, approved=True, name='Buyer Test', attestation=True)
        with self.assertRaises(ValueError):
            respond(self.store, invitation['token'], approved=False, name='Another person', note='Changed mind')

    def test_mail_decision_cannot_be_overwritten_from_workspace(self):
        invitation = create_invitation(self.store, self.invoice['id'], 'buyer@example.com', 'https://example.com')
        respond(self.store, invitation['token'], approved=True, name='Buyer Test', attestation=True)
        current = next(i for i in self.store.load() if i['id'] == self.invoice['id'])
        with self.assertRaises(ValueError):
            respond_in_workspace(self.store, current, self.company, approved=False, name='Another person', note='Changed mind')


if __name__ == '__main__':
    unittest.main()
