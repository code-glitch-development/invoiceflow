"""Tests d'intégration exécutables après installation des dépendances."""
import importlib.util
from pathlib import Path
import unittest

HAS_STREAMLIT = importlib.util.find_spec('streamlit') is not None


@unittest.skipUnless(HAS_STREAMLIT, 'Streamlit doit être installé pour tester l’interface.')
class InterfaceTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(Path(__file__).with_name('app.py')), default_timeout=20).run()

    def test_all_screens(self):
        at = self.app()
        for profile in ['PME', 'Client final', 'Investisseur']:
            at.sidebar.selectbox[0].set_value(profile).run()
            for page in ['Vue d’ensemble', 'Déposer une facture', 'Validation client', 'Financement', 'Simulateur', 'Portefeuille']:
                at.sidebar.radio[0].set_value(page).run()
                self.assertFalse(at.exception, (profile, page, list(at.exception)))

    def test_financing_and_payment(self):
        at = self.app()
        at.sidebar.selectbox[0].set_value('Investisseur').run()
        at.sidebar.radio[0].set_value('Financement').run()
        button = next(b for b in at.button if b.label == 'Simuler le financement')
        self.assertFalse(button.disabled)
        button.click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['invoices'][0]['status'], 'Financée')
        at.sidebar.radio[0].set_value('Portefeuille').run()
        next(b for b in at.button if b.label == 'Enregistrer le suivi').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['invoices'][0]['status'], 'Clôturée')


if __name__ == '__main__':
    unittest.main()
