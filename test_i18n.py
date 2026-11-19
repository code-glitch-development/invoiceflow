"""Localization checks that do not require a running Streamlit server."""
import unittest
from string import Formatter
import pandas as pd
from engine import seed, eligible
from i18n import FR, Translator, localize_frame


class LocalizationTests(unittest.TestCase):
    def test_templates_preserve_placeholders_and_user_values(self):
        def fields(template):
            return {field for _, field, _, _ in Formatter().parse(template) if field is not None}
        for english, french in FR.items():
            self.assertEqual(fields(english), fields(french), english)
        text = 'Invoice {p0} submitted. Switch to the Buyer role to confirm it.'
        reference = 'INV-{customer}-2026'
        self.assertIn(reference, Translator('FR').text(text, p0=reference))
        self.assertEqual(Translator('FR').text('custom note {unchanged}'), 'custom note {unchanged}')

    def test_exports_translate_states_without_changing_user_data(self):
        source = pd.DataFrame([{'Reference': 'Paid', 'SME': 'Strong', 'Buyer': 'Pending',
                                'Status': 'Financed', 'Amount (€)': 10000.0}])
        french = localize_frame(source, Translator('FR').text)
        self.assertEqual(french['Statut'][0], 'Financée')
        self.assertEqual(french['Référence'][0], 'Paid')
        self.assertEqual(french['PME'][0], 'Strong')
        self.assertEqual(french['Client final'][0], 'Pending')
        self.assertEqual(source['Status'][0], 'Financed')
        self.assertEqual(localize_frame(source, Translator('EN').text).to_dict(), source.to_dict())

    def test_changing_language_preserves_financing_eligibility(self):
        invoices = seed()
        initial = [(i['id'], i['status'], eligible(i), i['amount']) for i in invoices]
        for language in ['FR', 'EN', 'FR']:
            translate = Translator(language).text
            for invoice in invoices:
                translate(invoice['status'])
                translate(invoice['buyer_status'])
            self.assertEqual(initial, [(i['id'], i['status'], eligible(i), i['amount']) for i in invoices])


if __name__ == '__main__':
    unittest.main()
