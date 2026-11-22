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
        # Explicit test fixtures only: production startup now creates no invoices.
        import os
        from engine import seed
        from demo_catalog import catalog_examples
        from storage import InvoiceStore
        store = InvoiceStore(os.environ['INVOICEFLOW_DB_PATH'])
        store.initialize([])
        store.remove_builtin_demo_invoices()
        records = seed()
        records += catalog_examples(records)
        store.reset(records)

    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(Path(__file__).with_name('app.py')), default_timeout=20).run()

    def test_new_workspace_stays_empty_without_example_restore_actions(self):
        import os
        from streamlit.testing.v1 import AppTest
        from workspaces import WORKSPACES
        empty_path = str(Path(self.directory.name) / 'empty.db')
        with patch.dict('os.environ', {'INVOICEFLOW_DB_PATH': empty_path}):
            at = self.app()
            self.assertFalse(at.exception)
            self.assertEqual(at.session_state['invoices'], [])
            for role in ('SME', 'Buyer', 'Investor'):
                at.sidebar.selectbox(key='ui_demo_role').set_value(role).run()
                for page in WORKSPACES[role]['pages']:
                    at.sidebar.radio(key='ui_navigation').set_value(page).run()
                    self.assertFalse(at.exception)
                    self.assertEqual(at.session_state['invoices'], [])
            at.run()
            self.assertEqual(at.session_state['invoices'], [])
            self.assertNotIn('investor_add_examples', [b.key for b in at.button])

    def test_startup_removes_old_samples_and_preserves_user_invoice(self):
        import os
        from engine import seed, new_invoice
        from demo_catalog import catalog_examples
        from storage import InvoiceStore
        from datetime import date, timedelta
        path = str(Path(self.directory.name) / 'upgrade.db')
        store = InvoiceStore(path)
        records = seed()
        records += catalog_examples(records)
        custom = new_invoice(records, seller='My supplier', siren='987654321', buyer='My buyer',
            reference='REAL-001', amount=10000, issued=date.today(),
            due=date.today()+timedelta(days=60), documents=True, identity=True,
            strength='Strong', history='On time')
        store.initialize(records + [custom])
        before = store.load()[-1]
        with patch.dict('os.environ', {'INVOICEFLOW_DB_PATH': path}):
            at = self.app()
            self.assertFalse(at.exception)
            self.assertEqual(at.session_state['invoices'], [before])
            at.run()
            self.assertEqual(at.session_state['invoices'], [before])

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

    def test_opportunity_selection_survives_filters_language_and_comparison(self):
        at = self.app()
        at.sidebar.selectbox(key='ui_demo_role').set_value('Investor').run()
        identifiers = [i['id'] for i in at.session_state['invoices'] if i['reference'] in
                       ('NOV-2026-041', 'DEMO-INVEST-ATLAS')]
        for identifier in identifiers:
            at.checkbox(key='compare_' + identifier).check().run()
        self.assertEqual(at.session_state['investor_selection'], identifiers)
        at.number_input(key='inv_budget').set_value(10000.0).run()
        self.assertEqual(at.session_state['investor_selection'], identifiers)
        self.assertTrue(at.button(key='review_selection').disabled)
        self.assertTrue(any('hidden by your filters' in info.value for info in at.info))
        at.sidebar.radio(key='ui_navigation').set_value('Compare opportunities').run()
        at.sidebar.radio(key='language').set_value('FR').run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['investor_selection'], identifiers)
        self.assertTrue(any(df.value.astype(str).eq('Groupe Horizon').to_numpy().any() for df in at.dataframe))
        at.sidebar.radio(key='ui_navigation').set_value('Simulation assumptions').run()
        at.sidebar.radio(key='ui_navigation').set_value('Compare opportunities').run()
        self.assertEqual(at.number_input(key='inv_budget').value, 10000.0)
        self.assertEqual(at.session_state['investor_selection'], identifiers)
        at.number_input(key='inv_budget').set_value(25000.0).run()
        at.button(key='review_selection').click().run()
        self.assertFalse(at.exception)
        self.assertFalse(at.button(key='confirm_selection').disabled)

    def test_opportunity_review_invalidates_on_budget_or_assumption_change(self):
        at = self.app()
        at.sidebar.selectbox(key='ui_demo_role').set_value('Investor').run()
        identifier = at.session_state['invoices'][0]['id']
        at.checkbox(key='compare_' + identifier).check().run()
        at.button(key='review_selection').click().run()
        at.number_input(key='inv_budget').set_value(30000.0).run()
        self.assertFalse(at.exception)
        self.assertNotIn('confirm_selection', [b.key for b in at.button])
        at.button(key='review_selection').click().run()
        at.sidebar.radio(key='ui_navigation').set_value('Simulation assumptions').run()
        at.number_input(key='investor_cost_lgd_percent').set_value(80.0).run()
        at.sidebar.radio(key='ui_navigation').set_value('Overview').run()
        self.assertFalse(at.exception)
        self.assertNotIn('confirm_selection', [b.key for b in at.button])

    def test_opportunity_batch_confirm_saves_exact_review(self):
        at = self.app()
        at.sidebar.selectbox(key='ui_demo_role').set_value('Investor').run()
        identifiers = [c.key.removeprefix('compare_') for c in at.checkbox if c.key.startswith('compare_')][:3]
        self.assertEqual(len(identifiers), 3)
        for identifier in identifiers:
            at.checkbox(key='compare_' + identifier).check().run()
        at.button(key='review_selection').click().run()
        review = at.session_state['investor_review']
        at.button(key='confirm_selection').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.sidebar.radio(key='ui_navigation').value, 'Portfolio')
        saved = {i['id']: i for i in at.session_state['invoices']}
        for entry in review['rows']:
            actual = saved[entry['invoice']['id']]
            self.assertEqual(actual['status'], 'Financed')
            self.assertEqual(actual['financing']['advance'], entry['report']['advance'])
            self.assertEqual(actual['financing']['pricing']['snapshot_hash'], entry['report']['snapshot_hash'])

    def test_open_dossier_preserves_card_quote(self):
        at = self.app()
        at.sidebar.selectbox(key='ui_demo_role').set_value('Investor').run()
        invoice = next(i for i in at.session_state['invoices'] if i['reference'] == 'DEMO-INVEST-ATLAS')
        from opportunities import opportunities
        expected = next(e['report'] for e in opportunities(at.session_state['invoices']) if e['invoice']['id'] == invoice['id'])
        at.button(key='dossier_' + invoice['id']).click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.sidebar.radio(key='ui_navigation').value, 'Financing')
        metric = next(m.value for m in at.metric if m.label == 'Model maximum advance')
        self.assertEqual(metric, f"€{expected['advance']:,.2f}")

    def test_investor_dashboard_is_in_portfolio_and_card_returns_are_collapsed(self):
        from i18n import Translator
        from opportunities import filtered, opportunities
        from portfolio import holding_yield_percent, portfolio_summary
        at = self.app()
        at.sidebar.selectbox(key='ui_demo_role').set_value('Investor').run()
        for language in ('EN', 'FR'):
            at.sidebar.radio(key='language').set_value(language).run()
            translate = Translator(language).text
            summary = portfolio_summary(at.session_state['invoices'])
            monetary = lambda n: (f'{n:,.2f}'.replace(',', ' ').replace('.', ',') + ' €'
                                  if language == 'FR' else f'€{n:,.2f}')
            values = {m.label: m.value for m in at.metric}
            self.assertNotIn(translate('Outstanding capital'), values)
            self.assertNotIn(translate('Simulated repayments received'), values)
            self.assertNotIn('review_selection', [b.key for b in at.button])
            details = [e for e in at.expander if e.label == translate('Returns and payment details')]
            self.assertTrue(details)
            self.assertTrue(all(not e.proto.expanded for e in details))
            entries = filtered(opportunities(at.session_state['invoices']), 25000, 90)
            content = [m.value for m in at.markdown]
            for entry in entries:
                face, report = entry['invoice']['amount'], entry['report']
                self.assertIn(translate('Gross return over the operation') +
                              f" · **{holding_yield_percent(face, report['advance']):.2f} %**", content)
                self.assertIn(translate('Gross annual yield (continuous)') +
                              f" · **{report['annual_rate_percent']:.2f} %**", content)
            at.button(key='investor_portfolio_details').click().run()
            self.assertFalse(at.exception)
            self.assertEqual(at.sidebar.radio(key='ui_navigation').value, 'Portfolio')
            values = {m.label: m.value for m in at.metric}
            self.assertEqual(values[translate('Realized gross gains (simulation)')], monetary(summary['realized_gain']))
            self.assertEqual(values[translate('Overdue invoices')], str(summary['overdue_count']))
            at.sidebar.radio(key='ui_navigation').set_value('Overview').run()

    def test_guided_single_invoice_financing_without_editing_technical_inputs(self):
        from i18n import Translator
        for language in ('EN', 'FR'):
            at = self.app()
            at.sidebar.radio(key='language').set_value(language).run()
            at.sidebar.selectbox(key='ui_demo_role').set_value('Investor').run()
            t = Translator(language).text
            action = next(b for b in at.button if b.key and b.key.startswith('dossier_'))
            identifier = action.key.removeprefix('dossier_')
            self.assertEqual(action.label, t('Review this financing'))
            action.click().run()
            self.assertFalse(at.exception)
            self.assertEqual(at.sidebar.radio(key='ui_navigation').value, 'Financing')
            advanced = next(e for e in at.expander if e.label == t('Advanced pricing assumptions'))
            self.assertFalse(advanced.proto.expanded)
            self.assertFalse(at.button(key='ui_simulate_financing').disabled)
            at.button(key='ui_simulate_financing').click().run()
            self.assertFalse(at.exception)
            saved = next(i for i in at.session_state['invoices'] if i['id'] == identifier)
            self.assertEqual(saved['status'], 'Financed')
            at.sidebar.radio(key='ui_navigation').set_value('Portfolio').run()
            self.assertFalse(at.exception)
            self.assertTrue(any(m.label == t('Outstanding capital') for m in at.metric))

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
                                 [translate('Opportunities') if role == 'Investor' and p == 'Overview' else translate(p) for p in WORKSPACES[role]['pages']])
                if role == 'Investor':
                    self.assertTrue(any(translate('Choose your next financing opportunities') in h.value for h in at.title))
                    self.assertEqual(at.session_state['invoices'], records)
                    continue
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
        at.radio(key='ui_pricing_method').set_value('Manual assumptions').run()
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

    def test_future_value_simulator_uses_percent_and_years(self):
        from future_value import continuous_future_value, round_value
        at = self.app()
        at.sidebar.selectbox(key='ui_demo_role').set_value('Investor').run()
        at.sidebar.radio(key='ui_navigation').set_value('Simulator').run()
        at.slider(key='ui_fee').set_value(0.0).run()
        self.assertFalse(at.exception)
        metric = lambda label: next(m.value for m in at.metric if m.label == label)
        self.assertEqual(metric('Future value (simulation)'), '€10,512.71')
        at.number_input(key='ui_simulation_years').set_value(0.5).run()
        expected = round_value(continuous_future_value(10000, .5, 5))
        self.assertEqual(metric('Future value (simulation)'), f'€{expected:,.2f}')
        at.sidebar.radio(key='language').set_value('FR').run()
        self.assertFalse(at.exception)
        self.assertEqual(at.number_input(key='ui_simulation_years').value, .5)
        self.assertEqual(metric('Valeur future (simulation)'), f'{expected:,.2f}'.replace(',', ' ').replace('.', ',') + ' €')

    def test_internal_cohort_saves_a_locked_report(self):
        from datetime import date
        at = self.app()
        at.sidebar.selectbox(key='ui_demo_role').set_value('Investor').run()
        at.sidebar.radio(key='ui_navigation').set_value('Financing').run()
        self.assertEqual(at.radio(key='ui_pricing_method').value, 'Risk-based pricing')
        self.assertFalse(at.button(key='ui_simulate_financing').disabled)
        invoice = at.session_state['invoices'][0]
        prefix = 'pricing_' + invoice['id'] + '_'
        self.assertFalse(at.exception)
        self.assertFalse(at.button(key='ui_simulate_financing').disabled)
        initial_rate = float(next(m.value for m in at.metric if m.label == 'Calculated annual continuous rate (%)'))
        at.selectbox(key=prefix+'cohort_group').set_value('Simulated occasionally late buyers').run()
        new_rate = float(next(m.value for m in at.metric if m.label == 'Calculated annual continuous rate (%)'))
        self.assertGreater(new_rate, initial_rate)
        at.button(key='ui_simulate_financing').click().run()
        self.assertFalse(at.exception)
        saved = at.session_state['invoices'][0]['financing']
        self.assertEqual(saved['pricing']['assumptions']['annual_pd_percent'], 4)
        self.assertEqual(saved['pricing']['assumptions']['data_origin'], 'Illustrative assumptions')
        at.sidebar.radio(key='ui_navigation').set_value('Portfolio').run()
        self.assertFalse(any(w.key == 'interest_rate_'+invoice['id'] for w in at.number_input))
        at.toggle(key='future_projection_'+invoice['id']).set_value(True).run()
        at.date_input(key='future_date_'+invoice['id']).set_value(date.fromisoformat(saved['pricing']['expected_payment_on'])).run()
        self.assertFalse(at.exception)
        self.assertEqual(next(m.value for m in at.metric if m.label == 'Future value (simulation)'), f"€{invoice['amount']:,.2f}")

    def test_risk_pricing_stale_data_and_rate_limit_disable_funding(self):
        from datetime import timedelta
        from future_value import valuation_today
        at = self.app()
        at.sidebar.selectbox(key='ui_demo_role').set_value('Investor').run()
        at.sidebar.radio(key='ui_navigation').set_value('Financing').run()
        identity = at.session_state['invoices'][0]['id']
        prefix = 'pricing_' + identity + '_'
        at.radio(key=prefix+'pd_mode').set_value('Manual PD inputs').run()
        at.date_input(key=prefix+'source_date').set_value(valuation_today()-timedelta(days=400)).run()
        self.assertFalse(at.exception)
        self.assertTrue(at.button(key='ui_simulate_financing').disabled)
        self.assertTrue(any('maximum age' in e.value for e in at.error))
        at.date_input(key=prefix+'source_date').set_value(valuation_today()).run()
        at.number_input(key=prefix+'max_rate_percent').set_value(1.0).run()
        self.assertTrue(at.button(key='ui_simulate_financing').disabled)
        self.assertTrue(any('policy limit' in e.value for e in at.error))

    def test_risk_inputs_and_quote_survive_language_switch(self):
        at = self.app()
        at.sidebar.selectbox(key='ui_demo_role').set_value('Investor').run()
        at.sidebar.radio(key='ui_navigation').set_value('Financing').run()
        prefix = 'pricing_' + at.session_state['invoices'][0]['id'] + '_'
        rate = next(m.value for m in at.metric if m.label == 'Calculated annual continuous rate (%)')
        at.sidebar.radio(key='language').set_value('FR').run()
        self.assertFalse(at.exception)
        self.assertEqual(at.number_input(key=prefix+'annual_pd_percent').value, 2)
        self.assertEqual(next(m.value for m in at.metric if m.label == 'Taux annuel continu calculé (%)'), rate)
        self.assertFalse(at.button(key='ui_simulate_financing').disabled)

    def test_internal_cohort_is_explained_and_pd_is_read_only(self):
        at = self.app()
        at.sidebar.selectbox(key='ui_demo_role').set_value('Investor').run()
        at.sidebar.radio(key='ui_navigation').set_value('Financing').run()
        prefix = 'pricing_' + at.session_state['invoices'][0]['id'] + '_'
        self.assertEqual(at.radio(key=prefix+'pd_mode').value, 'Internal fictional cohort')
        self.assertTrue(at.number_input(key=prefix+'annual_pd_percent').disabled)
        self.assertTrue(at.selectbox(key=prefix+'data_origin').disabled)
        self.assertEqual(next(m.value for m in at.metric if m.label == 'Fictional buyers observed for one year'),'200')
        self.assertEqual(next(m.value for m in at.metric if m.label == 'Fictional buyers with a default'),'4')
        self.assertTrue(any('Invented annual cohort counts' in w.value for w in at.warning))
        self.assertTrue(any(m.label == 'Existing unpaid capital for this buyer' for m in at.metric))
        at.selectbox(key=prefix+'cohort_group').set_value('Simulated frequently late buyers').run()
        self.assertFalse(at.exception)
        self.assertEqual(at.number_input(key=prefix+'annual_pd_percent').value,10)
        at.sidebar.radio(key='language').set_value('FR').run()
        self.assertFalse(at.exception)
        self.assertEqual(at.selectbox(key=prefix+'cohort_group').value, 'Simulated frequently late buyers')
        self.assertEqual(at.number_input(key=prefix+'annual_pd_percent').value,10)

    def test_manual_pd_still_requires_a_source(self):
        at = self.app()
        at.sidebar.selectbox(key='ui_demo_role').set_value('Investor').run()
        at.sidebar.radio(key='ui_navigation').set_value('Financing').run()
        prefix = 'pricing_' + at.session_state['invoices'][0]['id'] + '_'
        at.radio(key=prefix+'pd_mode').set_value('Manual PD inputs').run()
        at.text_input(key=prefix+'source').set_value('').run()
        self.assertFalse(at.exception)
        self.assertTrue(at.button(key='ui_simulate_financing').disabled)
        at.sidebar.radio(key='language').set_value('FR').run()
        self.assertFalse(at.exception)
        self.assertEqual(at.radio(key=prefix+'pd_mode').value,'Manual PD inputs')
        self.assertTrue(at.button(key='ui_simulate_financing').disabled)

    def test_portfolio_future_value_is_saved_projected_and_stopped_at_payment(self):
        from datetime import timedelta
        from future_value import continuous_future_value, round_value, valuation_today
        at = self.app()
        at.sidebar.selectbox(key='ui_demo_role').set_value('Investor').run()
        at.sidebar.radio(key='ui_navigation').set_value('Financing').run()
        at.radio(key='ui_pricing_method').set_value('Manual assumptions').run()
        at.number_input(key='ui_financing_interest').set_value(7.0).run()
        at.button(key='ui_simulate_financing').click().run()
        invoice = at.session_state['invoices'][0]
        self.assertEqual(invoice['financing']['annual_interest_rate'], 7)
        self.assertEqual(invoice['financing']['financed_on'], valuation_today().isoformat())
        at.sidebar.radio(key='ui_navigation').set_value('Portfolio').run()
        identity = invoice['id']
        at.toggle(key='future_projection_' + identity).set_value(True).run()
        at.date_input(key='future_date_' + identity).set_value(valuation_today()+timedelta(days=365)).run()
        self.assertFalse(at.exception)
        future = round_value(continuous_future_value(invoice['financing']['advance'], 1, 7))
        self.assertEqual(next(m.value for m in at.metric if m.label == 'Future value (simulation)'), f'€{future:,.2f}')
        next(b for b in at.button if b.label == 'Save tracking update').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(next(m.value for m in at.metric if m.label == 'Theoretical interest'), '€0.00')
        self.assertEqual(next(m.value for m in at.metric if m.label == 'Days without payment'), '0')
        reopened = self.app()
        stored = reopened.session_state['invoices'][0]['financing']
        self.assertEqual(stored['annual_interest_rate'], 7)
        self.assertEqual(stored['paid_on'], valuation_today().isoformat())

    def test_legacy_interest_settings_require_explicit_save(self):
        import os
        from datetime import timedelta
        from engine import seed
        from future_value import valuation_today
        from storage import InvoiceStore
        records = seed()
        legacy = records[2]
        legacy['financing'].pop('annual_interest_rate')
        legacy['financing'].pop('financed_on')
        InvoiceStore(os.environ['INVOICEFLOW_DB_PATH']).reset(records)
        at = self.app()
        at.sidebar.selectbox(key='ui_demo_role').set_value('Investor').run()
        at.sidebar.radio(key='ui_navigation').set_value('Portfolio').run()
        at.selectbox(key='portfolio_pick').set_value(legacy['id']).run()
        self.assertFalse(at.exception)
        self.assertFalse(any(m.label == 'Future value (simulation)' for m in at.metric))
        at.date_input(key='interest_start_' + legacy['id']).set_value(valuation_today()-timedelta(days=2))
        at.number_input(key='interest_rate_' + legacy['id']).set_value(6.0)
        next(b for b in at.button if b.label == 'Save interest assumptions').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(next(m.value for m in at.metric if m.label == 'Days without payment'), '2')

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

