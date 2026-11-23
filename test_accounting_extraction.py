from datetime import date,timedelta
from hashlib import sha256
import unittest
from unittest.mock import patch
from accounting_extraction import parse_account_pages,extract_accounts,apply_accounts_upload,signed_amount
from accounting_dates import latest_accounts_check
from financial_risk import assess_buyer
from test_extraction import text_pdf


def account_lines(buyer='Buyer Inc',end=None):
    end=end or date.today()-timedelta(days=30)
    start=end-timedelta(days=364)
    return ['COMPTES ANNUELS','Denomination sociale : '+buyer,'SIREN : 987654321',
            'Exercice du '+start.strftime('%d/%m/%Y')+' au '+end.strftime('%d/%m/%Y'),
            'Montants en euros','Total actif : 1 000 000', 'Actif circulant net : 600 000',
            "Dettes a moins d'un an : 300 000", 'Capitaux propres : 400 000',
            'Benefices accumules non distribues : 200 000', 'EBIT : 80 000']


class AccountingExtractionTests(unittest.TestCase):
    def test_pdf_prefills_dates_entity_all_seven_figures_and_z(self):
        result=extract_accounts(text_pdf(account_lines()))
        self.assertEqual(len(result.values),7)
        self.assertEqual(result.fields['entity_name'],'Buyer Inc')
        self.assertEqual(result.fields['buyer_siren'],'987654321')
        self.assertEqual(result.values['total_liabilities'],600000)
        self.assertEqual(result.values['ebit'],80000)
        self.assertTrue(result.evidence['ebit']['page'])
        self.assertFalse(result.used_ocr)

    def test_comparatives_choose_latest_column_in_either_order(self):
        for header,row in [('31/12/2025  |  31/12/2024','1000000  |  900000'),
                           ('31/12/2024  |  31/12/2025','900000  |  1000000'),
                           ('Exercice N  |  N-1','1000000  |  900000')]:
            result=parse_account_pages([header+'\nTotal actif : '+row])
            self.assertEqual(result.values['total_assets'],1000000)
        result=parse_account_pages(['Total actif : 1000000  |  900000'])
        self.assertNotIn('total_assets',result.values)

    def test_no_silent_column_merge_or_gross_net_confusion(self):
        result=parse_account_pages(['Exercice N  |  N-1\nTotal actif : 1 000 000 900 000'])
        self.assertNotIn('total_assets',result.values)
        result=parse_account_pages(['Brut  |  Amortissements  |  Net\nTotal actif : 1200000  |  200000  |  1000000'])
        self.assertEqual(result.values['total_assets'],1000000)
        result=parse_account_pages(['Brut  |  Amortissements\nTotal actif : 1200000  |  200000'])
        self.assertNotIn('total_assets',result.values)

    def test_units_negative_numbers_zero_and_missing_are_distinct(self):
        result=parse_account_pages(['Montants en milliers d’euros\nTotal actif : 1000\nCapitaux propres : (100)\nEBIT : -20\nBenefices accumules non distribues : 0'])
        self.assertEqual(result.values['total_assets'],1000000)
        self.assertEqual(result.values['equity'],-100000)
        self.assertEqual(result.values['ebit'],-20000)
        self.assertEqual(result.values['retained_earnings'],0)
        self.assertNotIn('current_liabilities',result.values)
        self.assertEqual(signed_amount('(1 234,56)'),-1234.56)
        self.assertEqual(signed_amount('0'),0)
        self.assertIsNone(signed_amount('-'))

    def test_ebitda_and_net_income_are_not_substituted_for_ebit(self):
        result=parse_account_pages(['EBITDA : 100000\nResultat net : 50000\nResultat d exploitation : 80000\nReport a nouveau : 10000'])
        self.assertNotIn('ebit',result.values)
        self.assertNotIn('retained_earnings',result.values)

    def test_conflicts_other_currency_and_multiple_entities_require_review(self):
        result=parse_account_pages(['Total actif : 1000000\nTotal actif : 2000000'])
        self.assertNotIn('total_assets',result.values)
        self.assertTrue(result.warnings)
        result=parse_account_pages(['USD\nTotal actif : 1000000'])
        self.assertNotIn('total_assets',result.values)
        result=parse_account_pages(['Denomination sociale : One\nDenomination sociale : Two'])
        self.assertNotIn('entity_name',result.fields)

    def test_replacement_clears_stale_values_and_same_file_preserves_manual_correction(self):
        state={};prefix='test_';data=text_pdf(account_lines())
        apply_accounts_upload(state,prefix,data)
        self.assertEqual(state[prefix+'total_assets'],1000000)
        state[prefix+'ebit']=95000
        self.assertFalse(apply_accounts_upload(state,prefix,data))
        self.assertEqual(state[prefix+'ebit'],95000)
        apply_accounts_upload(state,prefix,text_pdf(['COMPTES ANNUELS','EBIT : 1000']))
        self.assertIsNone(state[prefix+'total_assets'])
        self.assertEqual(state[prefix+'ebit'],1000)
        self.assertFalse(state[prefix+'reviewed'])

    def test_extracted_dates_and_siren_cannot_be_silently_changed_on_save(self):
        from test_financial_risk import fixture_accounts
        from financial_risk import validate_accounts
        invoice={'buyer':'Buyer Inc'}
        accounts=fixture_accounts(invoice)
        accounts['extraction']={'fields':{'period_end':'2024-12-31','buyer_siren':'987654321'}}
        accounts['extraction_reviewed']=True
        with self.assertRaisesRegex(ValueError,'differs'):
            validate_accounts(accounts,invoice['buyer'])
        accounts['extraction']['fields']['period_end']=accounts['period_end']
        accounts['extraction']['fields']['buyer_siren']='123456789'
        with self.assertRaisesRegex(ValueError,'SIREN differs'):
            validate_accounts(accounts,invoice['buyer'])
        accounts['extraction']['fields']['buyer_siren']='987654321'
        accounts['extraction_reviewed']=False
        with self.assertRaisesRegex(ValueError,'Review the extracted'):
            validate_accounts(accounts,invoice['buyer'])

    def test_removing_new_pdf_cannot_reuse_its_values_with_saved_source(self):
        from accounting_extraction import restore_saved_accounts
        state={};prefix='draft_';apply_accounts_upload(state,prefix,text_pdf(account_lines()))
        restore_saved_accounts(state,prefix,{})
        self.assertIsNone(state[prefix+'total_assets'])
        self.assertIsNone(state[prefix+'end'])
        self.assertNotIn(prefix+'prefill_hash',state)
        self.assertFalse(state[prefix+'reviewed'])

    def test_ocr_fallback_is_used_for_image_only_pdf(self):
        from pypdf import PdfWriter
        from io import BytesIO
        writer=PdfWriter();writer.add_blank_page(width=595,height=842);out=BytesIO();writer.write(out)
        with patch('accounting_extraction.ocr_image',return_value='\n'.join(account_lines())) as ocr:
            result=extract_accounts(out.getvalue())
            self.assertTrue(result.used_ocr)
            self.assertEqual(result.values['ebit'],80000)
            ocr.assert_called_once()


class AccountingDateTests(unittest.TestCase):
    def test_last_calendar_year_is_normal_not_fraud(self):
        result=latest_accounts_check('2025-12-31',date(2026,11,23))
        self.assertEqual(result['status'],'current')
        self.assertEqual(result['latest_completed'],'2025-12-31')
        self.assertNotIn('fraud',result)

    def test_old_year_is_rejected_after_preparation_window(self):
        self.assertEqual(latest_accounts_check('2024-12-31',date(2026,11,23))['status'],'obsolete')
        self.assertEqual(latest_accounts_check('2024-12-31',date(2026,2,15))['status'],'previous_in_preparation_window')

    def test_non_calendar_year_end_and_future_dates(self):
        self.assertEqual(latest_accounts_check('2025-06-30',date(2026,11,23))['status'],'previous_in_preparation_window')
        self.assertEqual(latest_accounts_check('2026-03-31',date(2026,11,23))['status'],'current')
        self.assertEqual(latest_accounts_check('2026-12-31',date(2026,11,23))['status'],'future')
