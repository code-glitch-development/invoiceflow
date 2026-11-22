from pathlib import Path
import tempfile
import unittest

from engine import eligible, finance
from opportunities import opportunities
from requested_examples import requested_supplier_examples
from storage import InvoiceStore


class RequestedExamplesTests(unittest.TestCase):
    def test_ten_distinct_suppliers_and_identical_explainable_quotes(self):
        records = requested_supplier_examples([])
        self.assertEqual(len(records), 10)
        for field in ('id', 'key', 'seller', 'siren', 'reference'):
            self.assertEqual(len({i[field] for i in records}), 10)
        self.assertTrue(all(eligible(i) for i in records))
        self.assertTrue(all(i['amount'] == 10000 and i['seller'].startswith('Démo') for i in records))
        self.assertEqual(requested_supplier_examples(records), [])
        offers = opportunities(records)
        self.assertEqual(len(offers), 10)
        self.assertTrue(all(e['report']['acceptable'] for e in offers))
        self.assertEqual(len({e['report']['annual_rate_percent'] for e in offers}), 1)

    def test_batch_is_once_only_preserves_edits_and_stays_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            store = InvoiceStore(Path(directory) / 'invoices.db')
            store.initialize([])
            store.remove_builtin_demo_invoices()
            self.assertEqual(store.add_requested_supplier_examples(), 10)
            invoice = store.load()[0]
            finance(invoice, 2, False, 0)
            saved = store.update(invoice)
            self.assertEqual(store.add_requested_supplier_examples(), 0)
            self.assertEqual(store.load()[0], saved)
            self.assertEqual(store.remove_builtin_demo_invoices(), 0)
            self.assertEqual(len(store.load()), 10)
            store.reset([])
            self.assertEqual(store.add_requested_supplier_examples(), 0)
            self.assertEqual(store.load(), [])


if __name__ == '__main__':
    unittest.main()
