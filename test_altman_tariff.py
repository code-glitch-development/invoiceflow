from copy import deepcopy
from datetime import timedelta
import math
from pathlib import Path
import tempfile
import unittest
from altman_tariff import tariff_quote
from engine import seed,finance_with_altman_tariff
from future_value import valuation_today,investor_valuation
from opportunities import tariff_opportunities,review_selection
from storage import InvoiceStore,StorageError
from test_financial_risk import with_accounts,fixture_accounts


class TariffTests(unittest.TestCase):
    def setUp(self):
        self.invoice=with_accounts(seed()[0]);self.invoice['amount']=10000
        self.invoice['due']=(valuation_today()+timedelta(days=60)).isoformat()

    def zone(self,value):
        self.invoice['buyer_accounts']=fixture_accounts(self.invoice,total_assets=1000000.0,
            total_liabilities=1000000.0,equity=0.0,current_assets=300000.0,current_liabilities=300000.0,
            retained_earnings=0.0,ebit=value*1000000/6.72)

    def test_user_selected_rates_premiums_and_boundary_categories(self):
        for z,rate,premium,accepted in [(2.601,5,0,True),(2.6,7,2,True),(1.1,7,2,True),(1.099,9,4,False)]:
            self.zone(z);report=tariff_quote(self.invoice)
            self.assertEqual(report['policy_annual_rate_percent'],rate)
            self.assertEqual(report['risk_premium_pp'],premium)
            self.assertEqual(report['acceptable'],accepted)
            self.assertNotIn('annual_pd_percent',report['assumptions'])

    def test_missing_accounts_are_explicitly_unknown_at_ten_percent(self):
        self.invoice.pop('buyer_accounts')
        report=tariff_quote(self.invoice)
        self.assertEqual(report['policy_annual_rate_percent'],10)
        self.assertEqual(report['risk_premium_pp'],5)
        self.assertEqual(report['accounting_status'],'Risk not assessed')
        self.assertIsNone(report['accounting_z'])
        self.assertTrue(report['acceptable'])

    def test_provided_but_invalid_accounts_do_not_bypass_review_at_ten_percent(self):
        self.invoice['buyer_accounts']['values']['ebit']=None
        report=tariff_quote(self.invoice)
        self.assertFalse(report['acceptable'])
        with self.assertRaises(ValueError):finance_with_altman_tariff(self.invoice)

    def test_exponential_duration_is_used_in_both_directions(self):
        r=tariff_quote(self.invoice)
        exact=10000*math.exp(-.05*60/365)
        self.assertLessEqual(r['advance'],exact)
        self.assertLess(exact-r['advance'],.011)
        self.assertAlmostEqual(r['advance']*math.exp((r['annual_rate_percent']/100)*60/365),10000)
        longer=deepcopy(self.invoice);longer['due']=(valuation_today()+timedelta(days=120)).isoformat()
        r2=tariff_quote(longer)
        self.assertEqual(r2['policy_annual_rate_percent'],5)
        self.assertGreater(r2['gross_discount'],r['gross_discount'])

    def test_financing_rechecks_risk_and_preserves_saved_tariff(self):
        report=tariff_quote(self.invoice)
        finance_with_altman_tariff(self.invoice)
        saved=self.invoice['financing']
        self.assertEqual(saved['advance'],report['advance'])
        self.assertEqual(saved['pricing']['snapshot_hash'],report['snapshot_hash'])
        self.assertEqual(investor_valuation(self.invoice,valuation_today()+timedelta(days=60))['future_value'],10000)

    def test_operational_checks_still_apply_when_accounts_missing(self):
        self.invoice.pop('buyer_accounts');self.invoice['buyer_status']='Disputed'
        with self.assertRaises(ValueError):finance_with_altman_tariff(self.invoice)

    def test_distress_tariff_is_indicative_and_cannot_be_funded_automatically(self):
        self.zone(.5)
        before=deepcopy(self.invoice)
        with self.assertRaises(ValueError):finance_with_altman_tariff(self.invoice)
        self.assertEqual(self.invoice,before)

    def test_tariff_batch_repricing_and_concurrency(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        store=InvoiceStore(Path(directory.name)/'test.db');store.initialize([self.invoice])
        records=store.load();entries=tariff_opportunities(records)
        review=review_selection(entries,[records[0]['id']],10000,records)
        result=store.finance_selection(review)
        self.assertEqual(result[0]['financing']['pricing']['model_version'],'altman-tariff-demo-v1')
        self.assertEqual(result[0]['financing']['advance'],entries[0]['report']['advance'])
        with self.assertRaises(StorageError):store.finance_selection(review)
