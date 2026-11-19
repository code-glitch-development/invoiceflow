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
        at = self.app()
        for profile in ['SME', 'Buyer', 'Investor']:
            at.sidebar.selectbox(key='ui_demo_role').set_value(profile).run()
            for page in ['Overview', 'Upload an invoice', 'Invoice checks', 'Buyer confirmation', 'Financing', 'Simulator', 'Portfolio']:
                at.sidebar.radio(key='ui_navigation').set_value(page).run()
                for language in ['FR', 'EN']:
                    at.sidebar.radio(key='language').set_value(language).run()
                    self.assertFalse(at.exception, (language, profile, page, list(at.exception)))

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
