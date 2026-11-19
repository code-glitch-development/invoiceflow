from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from engine import seed, confirm, canonical
from opportunities import (opportunities, extra_examples, filtered, review_selection,
                           review_fingerprint, assumptions_for)
from storage import InvoiceStore, StorageError


class OpportunityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = InvoiceStore(Path(self.directory.name) / 'demo.db')
        initial = seed()
        initial += extra_examples(initial)
        self.store.initialize(initial)
        self.records = self.store.load()
        self.entries = opportunities(self.records)
        self.ids = [e['invoice']['id'] for e in self.entries]

    def review(self, ids=None, budget=25000):
        return review_selection(self.entries, ids or self.ids, budget, self.records)

    def test_quotes_match_original_pricing_engine_and_cohorts(self):
        from risk_pricing import price_invoice
        self.assertEqual(len(self.entries), 3)
        for entry in self.entries:
            self.assertEqual(entry['report'], price_invoice(entry['invoice'], assumptions_for(entry['scenario'])))
            self.assertTrue(entry['report']['acceptable'])

    def test_same_buyer_scenario_is_consistent_across_invoices(self):
        confirm(self.records[1], True)
        entries = opportunities(self.records, {canonical('Groupe Horizon'): 'Stressed'})
        horizon = [e for e in entries if e['invoice']['buyer'] == 'Groupe Horizon']
        self.assertEqual(len(horizon), 2)
        self.assertEqual({e['report']['assumptions']['annual_pd_percent'] for e in horizon}, {10})

    def test_filter_uses_advance_horizon_and_scenario(self):
        self.assertFalse(filtered(self.entries, 1, 90))
        self.assertFalse(filtered(self.entries, 25000, 1))
        selected = filtered(self.entries, 10000, 90, 'Prudent')
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]['invoice']['buyer'], 'Maison Atlas')
        # Horizon includes the configured expected delay beyond due date.
        self.assertFalse(filtered(self.entries, 25000, 30))

    def test_total_budget_differs_from_individual_filter(self):
        visible = filtered(self.entries, 16000, 90)
        self.assertEqual(len(visible), 3)
        with self.assertRaisesRegex(ValueError, 'budget'):
            self.review(budget=16000)

    def test_empty_duplicate_and_unavailable_selection_rejected(self):
        for ids in [[], [self.ids[0]] * 2, ['missing']]:
            with self.assertRaises(ValueError):
                review_selection(self.entries, ids, 25000, self.records)

    def test_review_totals_and_fingerprint_change_with_budget_and_assumptions(self):
        first = self.review()
        self.assertEqual(first['repayment'], 25000)
        self.assertEqual(round(first['repayment'] - first['advance'], 2), first['gross_gain'])
        self.assertNotEqual(review_fingerprint(first), review_fingerprint(self.review(budget=30000)))
        updated = opportunities(self.records, costs={'lgd_percent': 70.0})
        self.assertNotEqual(review_fingerprint(first), review_fingerprint(
            review_selection(updated, self.ids, 25000, self.records)))

    def test_batch_saves_exact_quotes_and_versions(self):
        review = self.review()
        saved = self.store.finance_selection(review)
        self.assertEqual(len(saved), 3)
        for actual, expected in zip(saved, review['rows']):
            self.assertEqual(actual['financing']['advance'], expected['report']['advance'])
            self.assertEqual(actual['financing']['pricing']['snapshot_hash'], expected['report']['snapshot_hash'])
            self.assertEqual(actual['_version'], 2)
        self.assertFalse(opportunities(self.store.load()))
        with self.assertRaises(StorageError):
            self.store.finance_selection(review)

    def test_concurrent_update_rejects_batch_without_partial_save(self):
        review = self.review()
        changed = self.store.load()[1]
        confirm(changed, True)
        self.store.update(changed)
        before = self.store.load()
        with self.assertRaises(StorageError):
            self.store.finance_selection(review)
        self.assertEqual(self.store.load(), before)

    def test_invalid_second_invoice_rolls_back_first_update(self):
        # Construct an invalid persisted status that report fields alone do not cover.
        changed = self.store.load()[-1]
        changed['identity'] = False
        self.store.update(changed)
        records = self.store.load()
        review = self.review()
        review['versions'] = {i['id']: i['_version'] for i in records}
        before = self.store.load()
        with self.assertRaises(ValueError):
            self.store.finance_selection(review)
        self.assertEqual(self.store.load(), before)

    def test_tampered_quote_is_rejected(self):
        review = self.review()
        review['rows'][0]['report']['assumptions']['lgd_percent'] = 90
        before = self.store.load()
        with self.assertRaises(StorageError):
            self.store.finance_selection(review)
        self.assertEqual(self.store.load(), before)

    def test_low_budget_rejected_at_commit(self):
        review = self.review()
        review['budget'] = 1
        with self.assertRaises(ValueError):
            self.store.finance_selection(review)
        self.assertEqual(self.store.load(), self.records)

    def test_new_examples_are_append_only_and_idempotent(self):
        self.assertEqual(self.store.add_examples(), 0)
        self.assertEqual(self.store.load(), self.records)
        self.store.reset(seed())
        self.assertEqual(self.store.add_examples(), 2)
        before = self.store.load()
        self.assertEqual(self.store.add_examples(), 0)
        self.assertEqual(self.store.load(), before)

    def test_no_pd_dilution_when_another_invoice_is_added(self):
        before = opportunities(self.records)[0]['report']['assumptions']['annual_pd_percent']
        copies = [deepcopy(self.records[1]) for _ in range(100)]
        self.assertEqual(opportunities(self.records + copies)[0]['report']['assumptions']['annual_pd_percent'], before)
