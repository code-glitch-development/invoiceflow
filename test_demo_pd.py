from copy import deepcopy
from datetime import date
import unittest

from demo_pd import COHORTS, cohort_pd, demo_cohort
from engine import seed, buyer_outstanding_capital
from risk_pricing import price_invoice, stress_scenarios
from future_value import valuation_today
from test_risk_pricing import assumptions


def internal_assumptions(group='All simulated buyers'):
    data = assumptions()
    cohort = demo_cohort(group)
    data.update(annual_pd_percent=cohort['observed_pd_percent'], pd_cohort=cohort,
                source=cohort['dataset_version'], source_date=cohort['observation_end'],
                data_origin='Illustrative assumptions')
    return data


class DemoCohortTests(unittest.TestCase):
    def test_default_is_four_defaults_over_two_hundred_buyers(self):
        result = demo_cohort()
        self.assertEqual(result['borrowers'], 200)
        self.assertEqual(result['defaults'], 4)
        self.assertEqual(result['observed_pd_percent'], 2)
        self.assertTrue(result['synthetic'])

    def test_groups_are_disjoint_and_add_up_to_global_counts(self):
        groups = list(COHORTS.values())[1:]
        self.assertEqual(sum(n for n,d in groups), COHORTS['All simulated buyers'][0])
        self.assertEqual(sum(d for n,d in groups), COHORTS['All simulated buyers'][1])
        self.assertEqual(demo_cohort('Simulated occasionally late buyers')['observed_pd_percent'], 4)
        self.assertEqual(demo_cohort('Simulated frequently late buyers')['observed_pd_percent'], 10)

    def test_only_completed_calendar_year_used(self):
        result = demo_cohort(as_of=date(2026, 1, 1))
        self.assertEqual(result['observation_start'], '2025-01-01')
        self.assertEqual(result['observation_end'], '2026-01-01')
        self.assertEqual(demo_cohort(as_of=date(2026,12,31)), result)
        self.assertNotEqual(demo_cohort(as_of=date(2027,1,1))['dataset_version'], result['dataset_version'])

    def test_invalid_counts_and_empty_cohort(self):
        self.assertIsNone(cohort_pd(0,0))
        self.assertEqual(cohort_pd(100,0), 0)  # Observed frequency, not proof of zero true risk.
        for n,d in [(-1,0),(2,3),(2,-1),(True,1),(20.5,1),(10,True)]:
            with self.assertRaises(ValueError):
                cohort_pd(n,d)

    def test_snapshot_counts_and_source_are_preserved_in_quote(self):
        inputs = internal_assumptions()
        result = price_invoice(seed()[0], inputs)
        self.assertEqual(result['assumptions']['annual_pd_percent'], 2)
        self.assertEqual(result['assumptions']['pd_cohort'], demo_cohort())

    def test_cohort_cannot_be_relabelled_as_real_data_or_modified(self):
        original = internal_assumptions()
        for key,value in [('annual_pd_percent',9),('data_origin','User-provided, unverified'),
                           ('source_date',(date(2000,1,1)).isoformat())]:
            with self.assertRaises(ValueError):
                price_invoice(seed()[0], dict(original, **{key:value}))
        edited = deepcopy(original)
        edited['pd_cohort']['defaults'] = 99
        with self.assertRaises(ValueError):
            price_invoice(seed()[0], edited)

    def test_stress_is_hypothetical_and_does_not_corrupt_cohort(self):
        inputs = internal_assumptions()
        before = deepcopy(inputs)
        results = stress_scenarios(seed()[0], inputs)
        self.assertEqual(len(results),4)
        self.assertEqual(inputs,before)
        self.assertGreater(results[1]['annual_rate_percent'],results[0]['annual_rate_percent'])

    def test_group_change_updates_rate_and_no_workspace_event_is_read(self):
        invoice = seed()[0]
        low = price_invoice(invoice, internal_assumptions('Simulated on-time buyers'))
        high = price_invoice(invoice, internal_assumptions('Simulated frequently late buyers'))
        self.assertLess(low['annual_rate_percent'],high['annual_rate_percent'])
        self.assertEqual(demo_cohort()['defaults'],4)

    def test_transaction_growth_does_not_dilute_pd_and_unpaid_capital_grows(self):
        invoice = seed()[0]
        reference = demo_cohort()
        loan = dict(invoice, status='Financed', outcome=None, financing={'advance':1000.0})
        many_paid = [dict(loan,id=f'paid-{n}',status='Closed',outcome='Paid') for n in range(100)]
        before = buyer_outstanding_capital([loan],invoice['buyer'])
        after_paid = buyer_outstanding_capital([loan]+many_paid,invoice['buyer'])
        self.assertEqual(before,after_paid)
        after_unpaid = buyer_outstanding_capital([loan,dict(loan,id='second')]+many_paid,invoice['buyer'])
        self.assertEqual(after_unpaid['outstanding_capital'],2000)
        self.assertEqual(after_unpaid['advance_count'],2)
        self.assertEqual(demo_cohort(),reference)

    def test_other_buyers_and_disputes_do_not_change_cohort_counts(self):
        records = seed()
        records[1]['outcome'] = 'Dispute'
        records[1]['buyer'] = 'Different client'
        exposure = buyer_outstanding_capital(records,records[0]['buyer'])
        self.assertEqual(exposure['outstanding_capital'],0)
        self.assertEqual(demo_cohort()['defaults'],4)


if __name__ == '__main__':
    unittest.main()
