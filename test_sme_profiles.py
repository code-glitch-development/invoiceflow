from copy import deepcopy
import unittest

from engine import seed
from sme_profiles import (ALL_SMES, DEMO_SMES, company_profiles, sme_invoices,
                          apply_sme_profile, validate_sme_submission)


class SMEProfileTests(unittest.TestCase):
    def test_profiles_include_pdf_suppliers_and_do_not_create_or_change_invoices(self):
        records = seed()
        original = deepcopy(records)
        profiles = company_profiles(records)
        self.assertEqual(len(DEMO_SMES), 10)
        self.assertEqual(profiles['Atelier Nova Conseil SAS'], '123456789')
        self.assertEqual(profiles['Orbe Digital SAS'], '234567890')
        for i in records:
            self.assertEqual(profiles[i['seller']], i['siren'])
        self.assertEqual(records, original)
        self.assertEqual(sme_invoices([], 'Orbe Digital SAS'), [])

    def test_filter_only_selected_supplier_and_preserve_aggregate_view(self):
        records = seed()
        matching = sme_invoices(records, ' atelier nova ')
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]['seller'], 'Atelier Nova')
        self.assertEqual(sme_invoices(records, ALL_SMES), records)
        self.assertEqual(sme_invoices(records, ''), [])

    def test_switch_clears_previous_invoice_file_and_preserves_unrelated_state(self):
        state = dict(sme_active_profile='Orbe Digital SAS', ui_sme_name='Orbe Digital SAS',
            ui_siren_9_digit_format='234567890', ui_buyer='Old buyer', ui_invoice_reference='OLD',
            ui_original_invoice_pdf_png_or_jpeg_10_mb_max=b'old pdf', invoice_prefill_digest='old hash',
            language='FR', signature_pick='guided-invoice')
        apply_sme_profile(state, 'Atelier Nova Conseil SAS', DEMO_SMES)
        self.assertEqual(state['ui_sme_name'], 'Atelier Nova Conseil SAS')
        self.assertEqual(state['ui_siren_9_digit_format'], '123456789')
        for key in ('ui_buyer', 'ui_invoice_reference', 'ui_original_invoice_pdf_png_or_jpeg_10_mb_max', 'invoice_prefill_digest'):
            self.assertNotIn(key, state)
        self.assertEqual(state['language'], 'FR')
        self.assertEqual(state['signature_pick'], 'guided-invoice')

    def test_reruns_preserve_edits_but_aggregate_switch_clears_draft(self):
        state = dict(sme_active_profile='Orbe Digital SAS', ui_sme_name='Edited', ui_invoice_reference='NEW')
        original = deepcopy(state)
        apply_sme_profile(state, 'Orbe Digital SAS', DEMO_SMES)
        self.assertEqual(state, original)
        apply_sme_profile(state, ALL_SMES, DEMO_SMES)
        self.assertNotIn('ui_invoice_reference', state)
        self.assertNotIn('ui_sme_name', state)

    def test_mismatched_pdf_supplier_cannot_be_submitted_under_named_profile(self):
        with self.assertRaises(ValueError):
            validate_sme_submission('Orbe Digital SAS', 'Atelier Nova Conseil SAS')
        validate_sme_submission('Orbe Digital SAS', ' orbe digital sas ')
        validate_sme_submission(ALL_SMES, 'Any new company')


if __name__ == '__main__':
    unittest.main()
