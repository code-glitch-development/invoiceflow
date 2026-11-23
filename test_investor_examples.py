from copy import deepcopy
from datetime import date
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from accounting_extraction import extract_accounts
from altman_tariff import tariff_quote
from engine import finance_with_altman_tariff
from financial_risk import assess_buyer
from investor_examples import investor_examples
from storage import InvoiceStore


class InvestorExampleTests(unittest.TestCase):
    def test_five_cases_cover_risk_zones_and_unknown_without_seeding_database(self):
        with tempfile.TemporaryDirectory() as directory:
            store = InvoiceStore(Path(directory)/'uploaded.db'); store.initialize([])
            cases = investor_examples()
            self.assertEqual(len(cases), 5)
            self.assertEqual(len({c['invoice']['id'] for c in cases}), 5)
            reports = [tariff_quote(c['invoice']) for c in cases]
            self.assertEqual([r['policy_annual_rate_percent'] for r in reports], [5,7,7,9,10])
            self.assertEqual([r['acceptable'] for r in reports], [True,True,True,False,True])
            self.assertEqual(store.load(), [])
            self.assertTrue(all(c['invoice']['investor_example'] for c in cases))

    def test_example_accounts_pdf_matches_inputs_hash_and_company(self):
        for case in investor_examples():
            invoice, pdf = case['invoice'], case['accounts_pdf']
            if not pdf:
                self.assertIsNone(assess_buyer(invoice)['value'])
                continue
            accounts = invoice['buyer_accounts']
            extracted = extract_accounts(pdf)
            self.assertEqual(extracted.values, accounts['values'])
            self.assertEqual(extracted.fields['entity_name'], invoice['buyer'])
            self.assertEqual(accounts['document']['sha256'], sha256(pdf).hexdigest())
            self.assertAlmostEqual(accounts['values']['total_assets'], accounts['values']['equity']+accounts['values']['total_liabilities'])

    def test_simulation_is_local_and_leaves_pending_checks_unverified(self):
        cases = investor_examples()
        untouched = deepcopy(cases[1:])
        invoice = cases[0]['invoice']
        finance_with_altman_tariff(invoice)
        self.assertEqual(invoice['status'], 'Financed')
        self.assertFalse(invoice['identity'])
        self.assertFalse(invoice['documents'])
        self.assertEqual(cases[1:], untouched)
        self.assertEqual(invoice['financing']['platform_commission'], 120)

    def test_generation_uses_current_annual_period_and_future_maturities(self):
        today = date(2027, 11, 23)
        for case in investor_examples(today):
            invoice = case['invoice']
            self.assertGreater(date.fromisoformat(invoice['due']), today)
            if case['accounts_pdf']:
                self.assertEqual(invoice['buyer_accounts']['period_end'], '2026-12-31')
                self.assertIsNotNone(assess_buyer(invoice, today)['value'])


if __name__ == '__main__':
    unittest.main()
