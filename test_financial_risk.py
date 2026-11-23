"""Published-formula, evidence and stale-data tests; fixtures never enter production data."""
from copy import deepcopy
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from financial_risk import assess_buyer, validate_accounts, save_buyer_accounts, statement_document
from storage import InvoiceStore


def fixture_accounts(invoice, **values):
    # Explicit synthetic test-only annual statements. Never auto-loaded by the app.
    end=date.today()-timedelta(days=30)
    data=dict(total_assets=1000000.0,current_assets=600000.0,current_liabilities=300000.0,
              total_liabilities=600000.0,equity=400000.0,retained_earnings=200000.0,ebit=80000.0)
    data.update(values)
    return dict(entity_name=invoice['buyer'],buyer_siren='987654321',company_type='non_financial_non_manufacturing',
        period_start=(end-timedelta(days=364)).isoformat(),period_end=end.isoformat(),
        source_reference='TEST FIXTURE ONLY — synthetic annual accounts, pages 1-2',values=data,
        document=dict(filename='TEST-synthetic-accounts.pdf',sha256=sha256(b'TEST FIXTURE ONLY').hexdigest()))


def with_accounts(invoice):
    invoice['buyer_accounts']=fixture_accounts(invoice)
    return invoice


def fixture_new_invoice(*args,**kwargs):
    from engine import new_invoice
    return with_accounts(new_invoice(*args,**kwargs))


def fixture_seed():
    from engine import seed
    return [with_accounts(i) for i in seed()]


class FinancialRiskTests(unittest.TestCase):
    def setUp(self):
        from engine import seed
        self.invoice=seed()[0]
        self.accounts=fixture_accounts(self.invoice)

    def test_no_old_dropdown_or_checkbox_can_generate_risk_without_accounts(self):
        from engine import score
        for strength in ['Strong','Average','Weak']:
            self.invoice.update(strength=strength,identity=True,documents=True,buyer_status='Confirmed')
            self.assertIsNone(assess_buyer(self.invoice)['value'])
            self.assertEqual(score(self.invoice),(None,{}))

    def test_unassessed_or_stale_accounting_blocks_risk_priced_financing(self):
        from engine import finance_with_risk_pricing
        from test_risk_pricing import assumptions
        for data in (None,self.accounts):
            invoice=deepcopy(self.invoice)
            if data:
                invoice['buyer_accounts']=deepcopy(data)
                invoice['buyer_accounts']['period_end']=(date.today()-timedelta(days=600)).isoformat()
            before=deepcopy(invoice)
            with self.assertRaises(ValueError):finance_with_risk_pricing(invoice,assumptions(),False,0)
            self.assertEqual(invoice,before)

    def test_known_published_formula_without_intercept_or_100_scale(self):
        self.invoice['buyer_accounts']=self.accounts
        report=assess_buyer(self.invoice)
        expected=6.56*0.3+3.26*0.2+6.72*0.08+1.05*(400000/600000)
        self.assertAlmostEqual(report['value'],expected)
        self.assertEqual(report['band'],'Lower distress zone')
        self.assertEqual(report['current_ratio'],2)
        self.assertEqual(report['equity_ratio_percent'],40)
        self.assertNotIn('pd',report)
        self.assertNotIn('yield',report)

    def test_missing_nan_infinite_zero_and_inconsistent_inputs_never_produce_score(self):
        patches=[dict(ebit=None),dict(ebit=float('nan')),dict(ebit=float('inf')),dict(total_assets=0),
                 dict(total_liabilities=0),dict(current_liabilities=-1),dict(current_assets=2000000),dict(equity=1)]
        for patch in patches:
            accounts=deepcopy(self.accounts);accounts['values'].update(patch)
            self.invoice['buyer_accounts']=accounts
            self.assertIsNone(assess_buyer(self.invoice)['value'],patch)
        self.accounts['values'].pop('ebit');self.invoice['buyer_accounts']=self.accounts
        self.assertIsNone(assess_buyer(self.invoice)['value'])

    def test_scope_entity_period_source_and_document_are_required(self):
        for patch in [dict(entity_name='Supplier'),dict(company_type='bank'),dict(buyer_siren='invalid'),
                      dict(period_start=date.today().isoformat()),dict(source_reference=''),dict(document={})]:
            self.invoice['buyer_accounts']=self.accounts|patch
            self.assertIsNone(assess_buyer(self.invoice)['value'],patch)

    def test_stale_and_future_accounts_have_no_current_risk(self):
        self.invoice['buyer_accounts']=self.accounts
        end=date.fromisoformat(self.accounts['period_end'])
        self.assertEqual(assess_buyer(self.invoice,today=end+timedelta(days=548))['status'],'assessed')
        self.assertIsNone(assess_buyer(self.invoice,today=end+timedelta(days=549))['value'])
        self.assertIsNone(assess_buyer(self.invoice,today=end-timedelta(days=1))['value'])

    def test_zone_thresholds_and_negative_earnings_are_not_clamped(self):
        # Zero X1/X2/X4 and an exactly controlled X3 give known boundary values.
        for target,band in [(1.099,'Distress zone'),(1.1,'Grey zone'),(2.6,'Grey zone'),(2.601,'Lower distress zone'),(-2,'Distress zone')]:
            values=dict(total_assets=1000000.0,total_liabilities=1000000.0,equity=0.0,
                        current_assets=300000.0,current_liabilities=300000.0,retained_earnings=0.0,
                        ebit=target*1000000/6.72)
            self.invoice['buyer_accounts']=fixture_accounts(self.invoice,**values)
            self.assertEqual(assess_buyer(self.invoice)['band'],band)

    def test_evidence_archive_atomic_save_readonly_financed_and_reset(self):
        from test_extraction import text_pdf
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        store=InvoiceStore(Path(directory.name)/'test.db');store.initialize([self.invoice])
        invoice=store.load()[0];pdf=text_pdf()
        save_buyer_accounts(store,invoice,self.accounts,pdf,'annual-accounts.pdf')
        actual=store.load()[0]
        self.assertEqual(statement_document(store,actual),pdf)
        self.assertEqual(actual['buyer_accounts']['document']['sha256'],sha256(pdf).hexdigest())
        self.assertFalse(actual['buyer_accounts'].get('verified',False))
        with self.assertRaises(ValueError): save_buyer_accounts(store,invoice,self.accounts,pdf,'stale.pdf')
        current=store.load()[0]
        save_buyer_accounts(store,current,self.accounts)
        self.assertEqual(statement_document(store,store.load()[0]),pdf)
        current=store.load()[0];current['financing']={'advance':9000};store.update(current)
        with self.assertRaises(ValueError): save_buyer_accounts(store,store.load()[0],self.accounts,pdf,'new.pdf')
        store.reset([])
        with store.transaction() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM buyer_account_documents').fetchone()[0],0)

    def test_missing_or_unreadable_pdf_does_not_save_fake_provenance(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        store=InvoiceStore(Path(directory.name)/'test.db');store.initialize([self.invoice])
        for data in [None,b'not a PDF',b'']:
            before=store.load()
            with self.assertRaises(ValueError):save_buyer_accounts(store,before[0],self.accounts,data,'bad.pdf')
            self.assertEqual(store.load(),before)
