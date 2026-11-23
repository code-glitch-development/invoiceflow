from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from buyer_account_profiles import (load_buyer_profile, save_buyer_profile_accounts,
    profile_statement_document, sync_buyer_profile_accounts)
from engine import seed, finance
from financial_risk import assess_buyer, statement_document
from storage import InvoiceStore
from test_extraction import text_pdf
from test_financial_risk import fixture_accounts


class BuyerAccountProfileTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.store = InvoiceStore(Path(self.directory.name)/'accounts.db'); self.store.initialize([])
        self.company = 'Lumen Services SAS'
        self.profile = load_buyer_profile(self.store, self.company)
        self.accounts = fixture_accounts(self.profile)
        self.pdf = text_pdf()

    def save(self, profile=None, accounts=None):
        save_buyer_profile_accounts(self.store, profile or self.profile,
                                   accounts or self.accounts, self.pdf, 'annual.pdf')

    def test_save_before_any_invoice_and_reopen_preserve_pdf_and_indicator(self):
        self.save()
        self.assertEqual(self.store.load(), [])
        reopened = InvoiceStore(self.store.path)
        profile = load_buyer_profile(reopened, self.company)
        self.assertEqual(profile['_version'], 1)
        self.assertEqual(profile_statement_document(reopened, profile), self.pdf)
        self.assertAlmostEqual(assess_buyer(profile)['value'], 3.8576)
        self.assertNotIn('financing', profile['buyer_accounts'])

    def test_existing_and_future_invoices_receive_matching_accounts_only(self):
        records = seed()
        records[0]['buyer'] = self.company
        self.store.reset(records)
        self.save()
        saved = self.store.load()
        self.assertEqual(saved[0]['buyer_accounts']['buyer_profile_id'], self.profile['id'])
        self.assertEqual(statement_document(self.store, saved[0]), self.pdf)
        self.assertNotIn('buyer_accounts', saved[1])
        future = deepcopy(records[1]); future.update(id='FUTURE', key='future', buyer=self.company)
        self.store.add(future)
        self.assertEqual(sync_buyer_profile_accounts(self.store), 1)
        later = self.store.load()[-1]
        self.assertAlmostEqual(assess_buyer(later)['value'], 3.8576)
        self.assertEqual(sync_buyer_profile_accounts(self.store), 0)

    def test_profile_updates_preserve_funded_and_invoice_specific_assessments(self):
        records = seed()
        for invoice in records: invoice['buyer'] = self.company
        records[1]['buyer_accounts'] = fixture_accounts(records[1], ebit=40000.0)
        self.store.reset(records); self.save()
        current = self.store.load()[0]
        finance(current, 4, False, 0); self.store.update(current)
        before = self.store.load()
        profile = load_buyer_profile(self.store, self.company)
        accounts = deepcopy(profile['buyer_accounts']); accounts['values']['ebit'] = 90000
        self.save(profile, accounts)
        after = self.store.load()
        for index in (0,1,2): self.assertEqual(after[index], before[index])
        self.assertEqual(after[3]['buyer_accounts']['values']['ebit'], 90000)
        self.assertEqual(after[3]['buyer_accounts']['buyer_profile_version'], 2)

    def test_stale_save_wrong_company_and_missing_source_rejected(self):
        with self.assertRaises(ValueError):
            save_buyer_profile_accounts(self.store, self.profile, self.accounts)
        wrong = deepcopy(self.accounts); wrong['entity_name'] = 'Another company'
        with self.assertRaises(ValueError): self.save(accounts=wrong)
        self.save()
        with self.assertRaises(ValueError): self.save()
        self.assertEqual(load_buyer_profile(self.store, self.company)['_version'], 1)

    def test_source_tampering_is_not_propagated_and_reset_clears_profiles(self):
        self.save()
        with self.store.transaction() as db:
            db.execute('UPDATE buyer_profile_documents SET content=?', (b'tampered',))
        self.assertIsNone(profile_statement_document(self.store, load_buyer_profile(self.store, self.company)))
        self.assertEqual(sync_buyer_profile_accounts(self.store), 0)
        self.store.reset([])
        self.assertEqual(load_buyer_profile(self.store, self.company)['_version'], 0)


if __name__ == '__main__':
    unittest.main()
