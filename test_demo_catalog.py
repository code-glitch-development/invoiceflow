from copy import deepcopy
from datetime import date
from pathlib import Path
import tempfile
import unittest

from demo_catalog import catalog_examples
from engine import seed, eligible, settle
from opportunities import opportunities, filtered, extra_examples
from storage import InvoiceStore


class DemoCatalogTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = InvoiceStore(Path(directory.name) / 'demo.db')
        self.store.initialize(seed())

    def test_catalog_has_thirty_unique_varied_invoices(self):
        records = seed()
        records += catalog_examples(records)
        self.assertEqual(len(records), 30)
        self.assertEqual(len({i['key'] for i in records}), 30)
        self.assertEqual(len({i['id'] for i in records}), 30)
        self.assertEqual(sum(eligible(i) for i in records), 19)
        self.assertGreaterEqual(len(filtered(opportunities(records), 25000, 90)), 12)
        self.assertGreaterEqual(len({i['buyer'] for i in records}), 6)
        self.assertGreaterEqual(len({i['amount'] for i in records}), 20)
        self.assertGreaterEqual(len({i['due'] for i in records}), 8)
        self.assertEqual({i['status'] for i in records},
                         {'Approved', 'To review', 'Disputed', 'Financed', 'Closed'})
        self.assertTrue(all(date.fromisoformat(i['issued']) <= date.today() < date.fromisoformat(i['due']) for i in records))
        paid = next(i for i in records if i['outcome'] == 'Paid')
        self.assertEqual(paid['status'], 'Closed')
        self.assertLess(paid['financing']['financed_on'], paid['financing']['paid_on'])

    def test_existing_six_invoice_workspace_receives_twenty_four(self):
        records = self.store.load()
        for invoice in extra_examples(records):
            self.store.add(invoice)
        self.assertEqual(self.store.populate_demo_catalog(once=True), 24)
        self.assertEqual(len(self.store.load()), 30)

    def test_upgrade_preserves_edits_and_financing_without_duplication(self):
        invoice = self.store.load()[2]
        settle(invoice, 'Paid')
        self.store.update(invoice)
        before = deepcopy(self.store.load())
        self.assertEqual(self.store.populate_demo_catalog(once=True), 26)
        after = self.store.load()
        self.assertEqual(after[:4], before)
        self.assertEqual(len(after), 30)
        self.assertEqual(self.store.populate_demo_catalog(once=True), 0)
        self.assertEqual(self.store.populate_demo_catalog(), 0)
        self.assertEqual(self.store.load(), after)

    def test_completed_upgrade_does_not_recreate_deleted_examples_on_reload(self):
        self.store.populate_demo_catalog(once=True)
        self.store.reset([])
        self.assertEqual(self.store.populate_demo_catalog(once=True), 0)
        self.assertEqual(self.store.load(), [])

    def test_catalog_generation_is_append_only(self):
        records = seed()
        records += catalog_examples(records)
        saved = deepcopy(records)
        records[-1]['note'] = 'Edited sample'
        self.assertEqual(catalog_examples(records), [])
        self.assertEqual(records[:-1], saved[:-1])
        self.assertEqual(records[-1]['note'], 'Edited sample')
