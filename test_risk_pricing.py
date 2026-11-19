from copy import deepcopy
from datetime import timedelta, date
import hashlib
import json
import math
import unittest

from engine import seed, configure_interest, finance_with_risk_pricing, loss_scenario
from future_value import continuous_future_value, valuation_today
from risk_pricing import horizon_default_probability, price_invoice, stress_scenarios


def assumptions():
    return dict(annual_pd_percent=2.0, lgd_percent=60.0, funding_rate_percent=3.0,
                capital_charge_percent=1.0, target_margin_percent=2.0, upfront_cost=20.0,
                expected_delay_days=5, recovery_lag_days=90, max_rate_percent=100.0,
                max_data_age_days=365, data_origin='Illustrative assumptions',
                source='Synthetic unit-test data; not calibrated',
                source_date=valuation_today().isoformat(), notes='Nominal net recoveries before timing discount.')


class RiskPricingTests(unittest.TestCase):
    def setUp(self):
        self.invoice = seed()[0]
        self.inputs = assumptions()

    def test_annual_probability_is_scaled_by_survival_not_linearly(self):
        self.assertAlmostEqual(horizon_default_probability(20, 365), .20)
        self.assertAlmostEqual(horizon_default_probability(20, 730), 1-.8**2)
        self.assertAlmostEqual(horizon_default_probability(20, 30), 1-.8**(30/365))
        self.assertEqual(horizon_default_probability(0, 1000), 0)
        self.assertEqual(horizon_default_probability(20, 0), 0)

    def test_zero_risk_and_zero_cost_returns_full_face_value(self):
        inputs = dict(self.inputs, annual_pd_percent=0, funding_rate_percent=0,
                      capital_charge_percent=0, target_margin_percent=0, upfront_cost=0)
        result = price_invoice(self.invoice, inputs)
        self.assertTrue(result['acceptable'])
        self.assertEqual(result['advance'], self.invoice['amount'])
        self.assertEqual(result['annual_rate_percent'], 0)
        self.assertEqual(result['expected_npv'], 0)

    def test_cashflow_equation_and_conservative_cent_rounding(self):
        result = price_invoice(self.invoice, self.inputs)
        a, face = result['advance'], self.invoice['amount']
        p, years = result['horizon_pd'], result['years']
        b = math.log1p(.03+.01+.02)
        recovery = .40
        expected = ((1-p)*face*math.exp(-b*years) +
                    p*recovery*a*math.exp(-b*(years+90/365)) - a - 20)
        self.assertAlmostEqual(result['expected_npv'], expected)
        self.assertGreaterEqual(expected, -1e-8)
        self.assertLess(expected, .010001)
        self.assertAlmostEqual(result['base_effective_rate_percent'], 6)
        self.assertAlmostEqual(result['base_rate_percent'], 100*math.log1p(.06))

    def test_pd_lgd_and_cost_each_reduce_advance(self):
        base = price_invoice(self.invoice, self.inputs)
        for key, value in [('annual_pd_percent', 10), ('lgd_percent', 90),
                           ('funding_rate_percent', 7), ('capital_charge_percent', 4),
                           ('target_margin_percent', 5), ('upfront_cost', 100)]:
            altered = price_invoice(self.invoice, dict(self.inputs, **{key:value}))
            self.assertLess(altered['advance'], base['advance'], key)
            self.assertGreater(altered['annual_rate_percent'], base['annual_rate_percent'], key)

    def test_payment_and_recovery_delays_reduce_advance(self):
        base = price_invoice(self.invoice, self.inputs)
        for key, value in [('expected_delay_days', 35), ('recovery_lag_days', 365)]:
            altered = price_invoice(self.invoice, dict(self.inputs, **{key:value}))
            self.assertLess(altered['advance'], base['advance'])

    def test_future_value_reaches_face_at_expected_collection(self):
        result = price_invoice(self.invoice, self.inputs)
        self.assertAlmostEqual(continuous_future_value(result['advance'], result['years'],
                                                       result['annual_rate_percent']), self.invoice['amount'])

    def test_no_automatic_probability_from_demo_score(self):
        base = price_invoice(self.invoice, self.inputs)
        different = dict(self.invoice, strength='Weak', history='Frequent delays')
        result = price_invoice(different, self.inputs)
        self.assertEqual(result['annual_rate_percent'], base['annual_rate_percent'])
        self.assertEqual(result['horizon_pd'], base['horizon_pd'])

    def test_incomplete_untraceable_or_invalid_risk_data_rejected(self):
        patches = [dict(annual_pd_percent=None), dict(lgd_percent=None), dict(source=''),
                   dict(data_origin='Verified by magic'), dict(source_date='invalid'),
                   dict(source_date=(valuation_today()+timedelta(days=1)).isoformat()),
                   dict(annual_pd_percent=100), dict(annual_pd_percent=-1), dict(lgd_percent=101),
                   dict(lgd_percent=-1), dict(funding_rate_percent=float('nan')),
                   dict(capital_charge_percent=float('inf')), dict(upfront_cost=-1),
                   dict(expected_delay_days=0.5), dict(recovery_lag_days=-1),
                   dict(max_rate_percent=101), dict(annual_pd_percent=True)]
        for patch in patches:
            with self.assertRaises(ValueError, msg=str(patch)):
                price_invoice(self.invoice, dict(self.inputs, **patch))

    def test_stale_data_and_rate_policy_block_without_clipping_rate(self):
        stale = dict(self.inputs, source_date=(valuation_today()-timedelta(days=400)).isoformat())
        self.assertFalse(price_invoice(self.invoice, stale)['acceptable'])
        result = price_invoice(self.invoice, dict(self.inputs, max_rate_percent=1))
        self.assertFalse(result['acceptable'])
        self.assertGreater(result['annual_rate_percent'], 1)
        original = deepcopy(self.invoice)
        with self.assertRaises(ValueError):
            finance_with_risk_pricing(self.invoice, dict(self.inputs, max_rate_percent=1), False, 80)
        self.assertEqual(self.invoice, original)

    def test_costs_exceeding_receipts_produce_no_offer(self):
        result = price_invoice(self.invoice, dict(self.inputs, upfront_cost=20000))
        self.assertIsNone(result['advance'])
        self.assertIsNone(result['expected_npv'])
        self.assertFalse(result['acceptable'])

    def test_workflow_gates_remain_enforced(self):
        for key, value in [('identity', False), ('documents', False), ('buyer_status', 'Disputed')]:
            invoice = dict(self.invoice, **{key:value})
            before = deepcopy(invoice)
            with self.assertRaises(ValueError):
                finance_with_risk_pricing(invoice, self.inputs, False, 80)
            self.assertEqual(invoice, before)

    def test_snapshot_and_future_rate_are_saved_without_double_charging(self):
        expected = price_invoice(self.invoice, self.inputs)
        finance_with_risk_pricing(self.invoice, self.inputs, False, 80)
        funding = self.invoice['financing']
        self.assertEqual(funding['advance'], expected['advance'])
        self.assertEqual(funding['fee'], expected['gross_discount'])
        self.assertAlmostEqual(funding['advance']+funding['fee'], self.invoice['amount'])
        self.assertEqual(funding['annual_interest_rate'], expected['annual_rate_percent'])
        self.assertEqual(loss_scenario(self.invoice['amount'], funding['rate'], 80)['advance'], funding['advance'])
        self.inputs['annual_pd_percent'] = 50
        self.assertEqual(funding['pricing']['assumptions']['annual_pd_percent'], 2)

    def test_coverage_and_recourse_do_not_invent_recoveries(self):
        other = deepcopy(self.invoice)
        finance_with_risk_pricing(self.invoice, self.inputs, False, 0)
        finance_with_risk_pricing(other, self.inputs, True, 100)
        self.assertEqual(self.invoice['financing']['advance'], other['financing']['advance'])
        self.assertEqual(other['financing']['pricing']['assumptions']['lgd_percent'], 60)

    def test_risk_priced_rate_cannot_be_overwritten(self):
        finance_with_risk_pricing(self.invoice, self.inputs, False, 80)
        before = deepcopy(self.invoice)
        with self.assertRaises(ValueError):
            configure_interest(self.invoice, 1, valuation_today())
        self.assertEqual(self.invoice, before)

    def test_hash_reproducibility_and_repricing_context(self):
        first = price_invoice(self.invoice, self.inputs)
        self.assertEqual(first, price_invoice(self.invoice, self.inputs))
        fields = dict(first)
        digest = fields.pop('snapshot_hash')
        canonical = json.dumps(fields, sort_keys=True, separators=(',', ':'), allow_nan=False)
        self.assertEqual(hashlib.sha256(canonical.encode()).hexdigest(), digest)
        changed = price_invoice(dict(self.invoice, amount=12000), self.inputs)
        self.assertNotEqual(changed['snapshot_hash'], digest)

    def test_stresses_keep_inputs_unchanged_and_show_original_offer_npv(self):
        before = deepcopy(self.inputs)
        rows = stress_scenarios(self.invoice, self.inputs)
        self.assertEqual(self.inputs, before)
        self.assertEqual(len(rows), 4)
        for row in rows[1:]:
            self.assertLess(row['advance'], rows[0]['advance'])
            self.assertLess(row['npv_at_base_advance'], 0)

    def test_expired_invoice_is_not_priced(self):
        with self.assertRaises(ValueError):
            price_invoice(dict(self.invoice, due=valuation_today().isoformat()), self.inputs)


if __name__ == '__main__':
    unittest.main()
