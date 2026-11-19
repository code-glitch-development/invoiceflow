"""Integration tests available after installing dependencies."""
import importlib.util
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

HAS_STREAMLIT = importlib.util.find_spec('streamlit') is not None


@unittest.skipUnless(HAS_STREAMLIT, 'Install Streamlit to test the interface.')
class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.environment = patch.dict('os.environ', {'INVOICEFLOW_DB_PATH': str(Path(self.directory.name) / 'demo.db')})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(Path(__file__).with_name('app.py')), default_timeout=20).run()

    def test_all_screens(self):
        from workspaces import WORKSPACES
        at = self.app()
        for profile in ['SME', 'Buyer', 'Investor']:
            at.sidebar.selectbox(key='ui_demo_role').set_value(profile).run()
            for page in WORKSPACES[profile]['pages']:
                at.sidebar.radio(key='ui_navigation').set_value(page).run()
                for language in ['FR', 'EN']:
                    at.sidebar.radio(key='language').set_value(language).run()
                    self.assertFalse(at.exception, (language, profile, page, list(at.exception)))

    def test_upload_prefills_editable_fields_and_saves_corrections(self):
        from io import BytesIO
        from test_extraction import text_pdf
        upload = BytesIO(text_pdf())
        upload.name = 'invoice-test.pdf'
        with patch('streamlit.file_uploader', return_value=upload):
            at = self.app()
            at.sidebar.radio(key='ui_navigation').set_value('Upload an invoice').run()
            self.assertFalse(at.exception)
            self.assertEqual(at.text_input(key='ui_invoice_reference').value, 'AUTO-TEST-001')
            self.assertEqual(at.text_input(key='ui_sme_name').value, 'Atelier Exemple')
            self.assertEqual(at.number_input(key='ui_invoice_amount').value, 420.0)
            at.text_input(key='ui_sme_name').set_value('Corrected supplier').run()
            self.assertEqual(at.text_input(key='ui_sme_name').value, 'Corrected supplier')
            at.number_input(key='ui_invoice_amount').set_value(450.0).run()
            self.assertEqual(at.text_input(key='ui_sme_name').value, 'Corrected supplier')
            self.assertEqual(at.number_input(key='ui_invoice_amount').value, 450.0)
            at.sidebar.radio(key='language').set_value('FR').run()
            self.assertFalse(at.exception)
            self.assertEqual(at.text_input(key='ui_sme_name').value, 'Corrected supplier')
            self.assertEqual(at.number_input(key='ui_invoice_amount').value, 450.0)
            # Extraction must not mark verification declarations as completed.
            self.assertFalse(at.checkbox(key='ui_simulate_verified_sme_identity').value)
            next(b for b in at.button if b.label == 'Déposer la facture').click().run()
            self.assertFalse(at.exception)
            saved = next(i for i in at.session_state['invoices'] if i['reference'] == 'AUTO-TEST-001')
            self.assertEqual(saved['seller'], 'Corrected supplier')
            self.assertEqual(saved['amount'], 450.0)
            self.assertTrue(saved['file_hash'])

    def test_unreadable_upload_does_not_submit_or_crash(self):
        from io import BytesIO
        upload = BytesIO(b'invalid')
        upload.name = 'bad.pdf'
        with patch('streamlit.file_uploader', return_value=upload):
            at = self.app()
            count = len(at.session_state['invoices'])
            at.sidebar.radio(key='ui_navigation').set_value('Upload an invoice').run()
            self.assertFalse(at.exception)
            self.assertEqual(at.text_input(key='ui_invoice_reference').value, '')
            self.assertIsNone(at.number_input(key='ui_invoice_amount').value)
            next(b for b in at.button if b.label == 'Submit invoice').click().run()
            self.assertFalse(at.exception)
            self.assertTrue(at.error)
            self.assertEqual(len(at.session_state['invoices']), count)

    def test_role_switch_changes_interface_and_preserves_records(self):
        from i18n import Translator
        from workspaces import WORKSPACES, overview
        at = self.app()
        records = [dict(i) for i in at.session_state['invoices']]
        for language in ['EN', 'FR']:
            at.sidebar.radio(key='language').set_value(language).run()
            translate = Translator(language).text
            for role in ['Buyer', 'Investor', 'SME']:
                at.sidebar.selectbox(key='ui_demo_role').set_value(role).run()
                self.assertFalse(at.exception)
                self.assertEqual(at.sidebar.radio(key='ui_navigation').value, 'Overview')
                self.assertEqual(at.sidebar.radio(key='ui_navigation').options,
                                 [translate(p) for p in WORKSPACES[role]['pages']])
                expected, items = overview(role, records)
                self.assertEqual([m.label for m in at.metric], [translate(m[0]) for m in expected])
                self.assertTrue(any(translate(WORKSPACES[role]['headline']) in m.value for m in at.markdown))
                self.assertEqual(at.session_state['invoices'], records)
                at.button(key='workspace_primary_action').click().run()
                self.assertEqual(at.sidebar.radio(key='ui_navigation').value, WORKSPACES[role]['target'])
                self.assertFalse(at.exception)

    def test_language_change_keeps_role_page(self):
        at = self.app()
        at.sidebar.selectbox(key='ui_demo_role').set_value('Buyer').run()
        at.sidebar.radio(key='ui_navigation').set_value('Buyer confirmation').run()
        at.sidebar.radio(key='language').set_value('FR').run()
        self.assertFalse(at.exception)
        self.assertEqual(at.sidebar.selectbox(key='ui_demo_role').value, 'Buyer')
        self.assertEqual(at.sidebar.radio(key='ui_navigation').value, 'Buyer confirmation')

    def test_financing_and_payment(self):
        at = self.app()
        at.sidebar.selectbox(key='ui_demo_role').set_value('Investor').run()
        at.sidebar.radio(key='ui_navigation').set_value('Financing').run()
        button = next(b for b in at.button if b.label == 'Simulate financing')
        self.assertFalse(button.disabled)
        button.click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['invoices'][0]['status'], 'Financed')
        before = [dict(i) for i in at.session_state['invoices']]
        at.sidebar.radio(key='language').set_value('FR').run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['invoices'], before)
        self.assertEqual(at.sidebar.selectbox(key='ui_demo_role').value, 'Investor')
        self.assertEqual(at.sidebar.radio(key='ui_navigation').value, 'Financing')
        at.sidebar.radio(key='language').set_value('EN').run()
        at.sidebar.radio(key='ui_navigation').set_value('Portfolio').run()
        next(b for b in at.button if b.label == 'Save tracking update').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['invoices'][0]['status'], 'Closed')
        reopened = self.app()
        self.assertFalse(reopened.exception)
        self.assertEqual(reopened.session_state['invoices'][0]['status'], 'Closed')

    def test_next_step_targets_the_selected_invoice(self):
        at = self.app()
        # The second sample awaits buyer confirmation.
        invoice = at.session_state['invoices'][1]
        at.selectbox(key='overview_pick').set_value(invoice['id']).run()
        next(b for b in at.button if b.label == 'Next: buyer confirmation').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.sidebar.selectbox(key='ui_demo_role').value, 'Buyer')
        self.assertEqual(at.sidebar.radio(key='ui_navigation').value, 'Buyer confirmation')
        self.assertEqual(at.selectbox(key='confirm_pick').value, invoice['id'])


if __name__ == '__main__':
    unittest.main()

