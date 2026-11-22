from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from demo_catalog import catalog_examples
from engine import seed
from storage import InvoiceStore


class DemoCleanupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = InvoiceStore(Path(self.directory.name) / 'invoices.db')

    def samples(self):
        records = seed()
        return records + catalog_examples(records)

    def test_remove_all_shipped_samples_including_financed_and_paid(self):
        self.store.initialize(self.samples())
        self.assertEqual(self.store.remove_builtin_demo_invoices(), 30)
        self.assertEqual(self.store.load(), [])
        self.assertEqual(self.store.remove_builtin_demo_invoices(), 0)
        self.store.initialize(self.samples())
        self.assertEqual(self.store.load(), [])

    def test_preserve_custom_data_versions_and_uploaded_documents(self):
        records = self.samples()
        custom = deepcopy(records[0])
        custom.update(id='CUSTOM', key='987654321:demoexample', siren='987654321',
                      seller='My supplier', buyer='My buyer', reference='DEMO-EXAMPLE')
        records[1]['file_hash'] = 'user-uploaded-document'
        records[-1]['amount'] = 9999  # An edited sample still belongs to the shipped catalog.
        self.store.initialize(records + [custom])
        expected = [i for i in self.store.load() if i['id'] in (records[1]['id'], 'CUSTOM')]
        self.assertEqual(self.store.remove_builtin_demo_invoices(), 29)
        self.assertEqual(self.store.load(), expected)

    def test_reopening_empty_database_does_not_add_invoices(self):
        self.store.initialize([])
        self.assertEqual(self.store.remove_builtin_demo_invoices(), 0)
        reopened = InvoiceStore(self.store.path)
        reopened.initialize([])
        self.assertEqual(reopened.load(), [])


if __name__ == '__main__':
    unittest.main()
