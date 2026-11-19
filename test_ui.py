"""Integration tests available after installing dependencies."""
import importlib.util
from pathlib import Path
import unittest

HAS_STREAMLIT = importlib.util.find_spec('streamlit') is not None


@unittest.skipUnless(HAS_STREAMLIT, 'Install Streamlit to test the interface.')
class InterfaceTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(Path(__file__).with_name('app.py')), default_timeout=20).run()

    def test_all_screens(self):
        at = self.app()
        for profile in ['SME', 'Buyer', 'Investor']:
            at.sidebar.selectbox[0].set_value(profile).run()
            for page in ['Overview', 'Upload an invoice', 'Buyer confirmation', 'Financing', 'Simulator', 'Portfolio']:
                at.sidebar.radio[0].set_value(page).run()
                self.assertFalse(at.exception, (profile, page, list(at.exception)))

    def test_financing_and_payment(self):
        at = self.app()
        at.sidebar.selectbox[0].set_value('Investor').run()
        at.sidebar.radio[0].set_value('Financing').run()
        button = next(b for b in at.button if b.label == 'Simulate financing')
        self.assertFalse(button.disabled)
        button.click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['invoices'][0]['status'], 'Financed')
        at.sidebar.radio[0].set_value('Portfolio').run()
        next(b for b in at.button if b.label == 'Save tracking update').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['invoices'][0]['status'], 'Closed')


if __name__ == '__main__':
    unittest.main()
