import unittest
from engine import seed, eligible, finance
from i18n import FR
from workspaces import WORKSPACES, overview


class WorkspaceTests(unittest.TestCase):
    def test_each_role_has_its_own_actions_and_metrics(self):
        records = seed()
        snapshots = []
        for role, config in WORKSPACES.items():
            metrics, items = overview(role, records)
            self.assertIn(config['target'], config['pages'])
            snapshots.append(tuple(label for label, _, _ in metrics))
            if role == 'Buyer':
                self.assertTrue(all(i['buyer_status'] == 'Pending' for i in items))
                self.assertEqual(metrics[1][1], sum(i['amount'] for i in items))
            if role == 'Investor':
                self.assertTrue(all(eligible(i) for i in items))
                self.assertEqual(metrics[1][1], sum(i['amount'] for i in items))
        self.assertEqual(len(set(snapshots)), 3)
        self.assertNotIn('Financing', WORKSPACES['SME']['pages'])
        self.assertIn('Buyer', WORKSPACES)
        self.assertIn('Buyer confirmation', WORKSPACES['SME']['pages'])
        self.assertNotIn('Buyer confirmation', WORKSPACES['Investor']['pages'])

    def test_metrics_follow_financing_and_payment(self):
        records = seed()
        initial, _ = overview('Investor', records)
        invoice = next(i for i in records if eligible(i))
        finance(invoice, 4, False, 80)
        metrics, items = overview('Investor', records)
        self.assertNotIn(invoice, items)
        self.assertEqual(metrics[2][1], initial[2][1] + invoice['financing']['advance'])
        invoice['status'] = 'Closed'
        metrics, _ = overview('Investor', records)
        self.assertEqual(metrics[2][1], initial[2][1])

    def test_empty_queues(self):
        for role in WORKSPACES:
            metrics, items = overview(role, [])
            self.assertEqual(items, [])
            self.assertTrue(all(value == 0 for _, value, _ in metrics))

    def test_workspace_content_is_translated(self):
        for role, config in WORKSPACES.items():
            labels = [config[k] for k in ['title', 'headline', 'description', 'section', 'action']]
            labels.extend(config['pages'] + config['steps'])
            labels.extend(label for label, _, _ in overview(role, seed())[0])
            for label in labels:
                self.assertIn(label, FR)


if __name__ == '__main__':
    unittest.main()
