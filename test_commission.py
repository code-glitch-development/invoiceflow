"""Platform fees reconcile separately from investor returns and historical terms."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest

from altman_tariff import tariff_quote
from commission import commission_breakdown
from engine import finance, finance_with_altman_tariff, finance_with_risk_pricing, seed
from future_value import valuation_today
from opportunities import assumptions_for, review_selection, tariff_opportunities
from portfolio import portfolio_summary
from storage import InvoiceStore
from test_financial_risk import with_accounts
from workspaces import overview


class CommissionTests(unittest.TestCase):
    def invoice(self):
        i = with_accounts(seed()[0])
        i['amount'] = 10000
        i['due'] = (valuation_today() + timedelta(days=60)).isoformat()
        return i

    def test_tariff_cashflows_reconcile_without_changing_investor_return(self):
        i = self.invoice()
        q = tariff_quote(i)
        self.assertEqual(q['platform_commission'], 100)
        self.assertEqual(q['advance'], 9918.14)
        self.assertEqual(q['gross_discount'], 81.86)
        self.assertEqual(q['sme_net_proceeds'], 9818.14)
        self.assertEqual(q['total_sme_cost'], 181.86)
        self.assertEqual(q['policy_annual_rate_percent'], 5)
        finance_with_altman_tariff(i)
        f = i['financing']
        self.assertEqual(f['sme_net_proceeds'] + f['platform_commission'], f['advance'])
        self.assertEqual(f['sme_net_proceeds'] + f['total_sme_cost'], i['amount'])
        self.assertEqual(portfolio_summary([i])['potential_gain'], 81.86)
        self.assertEqual(overview('SME', [i])[0][2][1], 9818.14)

    def test_commission_is_once_on_face_not_on_duration_or_advance(self):
        i = self.invoice()
        q = tariff_quote(i)
        i['due'] = (valuation_today() + timedelta(days=120)).isoformat()
        longer = tariff_quote(i)
        self.assertEqual(q['platform_commission'], longer['platform_commission'])
        self.assertGreater(longer['total_sme_cost'], q['total_sme_cost'])
        self.assertEqual(commission_breakdown(123.45, 120)['platform_commission'], 1.23)
        self.assertEqual(commission_breakdown(100.5, 99)['platform_commission'], 1.01)

    def test_manual_and_expected_cashflow_financing_record_same_commission(self):
        for method in ('manual', 'expected'):
            i = self.invoice()
            if method == 'manual':
                finance(i, 4, False, 0)
            else:
                finance_with_risk_pricing(i, assumptions_for('Central'), False, 0)
            f = i['financing']
            self.assertEqual(f['platform_commission'], 100)
            self.assertAlmostEqual(f['sme_net_proceeds'], f['advance'] - 100)
            self.assertAlmostEqual(f['total_sme_cost'], f['fee'] + 100)
            if f.get('pricing'):
                self.assertEqual(f['pricing']['sme_net_proceeds'], f['sme_net_proceeds'])

    def test_persisted_batch_ignores_client_fee_and_recomputes_terms(self):
        with tempfile.TemporaryDirectory() as directory:
            store = InvoiceStore(Path(directory)/'commission.db')
            store.initialize([self.invoice()])
            records = store.load()
            offers = tariff_opportunities(records)
            review = review_selection(offers, [records[0]['id']], 10000, records)
            review['rows'][0]['report']['platform_commission'] = 0
            review['rows'][0]['report']['sme_net_proceeds'] = 9999
            saved = store.finance_selection(review)[0]['financing']
            self.assertEqual(saved['platform_commission'], 100)
            self.assertEqual(store.load()[0]['financing'], saved)
            self.assertEqual(saved['sme_net_proceeds'], offers[0]['report']['sme_net_proceeds'])

    def test_historical_financings_are_not_repriced_by_reading(self):
        i = self.invoice()
        finance(i, 4, False, 0)
        for key in commission_breakdown(10000, 9600):
            i['financing'].pop(key)
        original = deepcopy(i)
        self.assertEqual(overview('SME', [i])[0][2][1], 9600)
        self.assertEqual(portfolio_summary([i])['potential_gain'], 400)
        self.assertEqual(i, original)

    def test_nonpositive_net_is_blocked_without_mutating_invoice(self):
        i = self.invoice()
        original = deepcopy(i)
        with self.assertRaises(ValueError):
            finance(i, 99.5, False, 0)
        self.assertEqual(i, original)
        i['due'] = (valuation_today() + timedelta(days=365*100)).isoformat()
        report = tariff_quote(i)
        self.assertFalse(report['acceptable'])


if __name__ == '__main__':
    unittest.main()
