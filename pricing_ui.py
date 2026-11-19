"""Investor risk-pricing controls; no invented mapping from demo scores to PD."""
from datetime import date
import json
import pandas as pd
import streamlit as st

from future_value import valuation_today
from risk_pricing import ORIGINS, price_invoice, stress_scenarios


def load_example(prefix):
    example = dict(annual_pd_percent=2.0, lgd_percent=60.0, funding_rate_percent=3.0,
                   capital_charge_percent=1.0, target_margin_percent=2.0, upfront_cost=20.0,
                   expected_delay_days=5, recovery_lag_days=90, max_rate_percent=100.0,
                   max_data_age_days=365, data_origin='Illustrative assumptions',
                   source='Fictional example - not estimated from historical data',
                   source_date=valuation_today())
    for key, value in example.items():
        st.session_state[prefix + key] = value


def pricing_controls(invoice, t, euro):
    prefix = 'pricing_' + invoice['id'] + '_'
    st.subheader(t('Risk-based invoice pricing'))
    st.caption(t('Provide one-year buyer PD, net LGD and costs. The demo score and payment-history dropdown are not converted into default probabilities.'))
    st.button(t('Load explicitly fictional assumptions'), on_click=load_example, args=(prefix,),
              key=prefix+'example')
    a, b = st.columns(2)
    origin_key = prefix+'data_origin'
    previous = st.session_state.get(origin_key, ORIGINS[0])
    origin = a.selectbox(t('Risk-data origin'), ORIGINS, format_func=t, key=origin_key,
                         index=ORIGINS.index(previous) if previous in ORIGINS else 0)
    source = b.text_input(t('Source / provider / reference'), key=prefix+'source',
                          value=st.session_state.get(prefix+'source', ''))
    observed = a.date_input(t('Risk-data observation date'), value=st.session_state.get(prefix+'source_date', valuation_today()),
                            max_value=valuation_today(), key=prefix+'source_date')
    assumptions = dict(data_origin=origin, source=source,
                       source_date=observed.isoformat() if observed else '')
    fields = [
        ('annual_pd_percent', 'One-year buyer probability of default (%)', 0.0, 99.9, 0.1),
        ('lgd_percent', 'Nominal LGD before time discount (%)', 0.0, 100.0, 1.0),
        ('funding_rate_percent', 'Annual funding cost (%)', 0.0, 100.0, 0.1),
        ('capital_charge_percent', 'Annual capital charge (%)', 0.0, 100.0, 0.1),
        ('target_margin_percent', 'Annual target margin (%)', 0.0, 100.0, 0.1),
        ('upfront_cost', 'Upfront transaction costs (€)', 0.0, None, 1.0),
    ]
    for index, (key, label, minimum, maximum, step) in enumerate(fields):
        assumptions[key] = (a if index % 2 == 0 else b).number_input(
            t(label), min_value=minimum, max_value=maximum, step=step,
            value=st.session_state.get(prefix+key), key=prefix+key)
    st.caption(t('LGD must reflect justified net recoveries. A coverage slider or recourse toggle alone does not establish a recovery value.'))
    st.caption(t('The recovery lag is discounted separately. Do not enter an already-discounted LGD unchanged.'))
    assumptions['notes'] = st.text_area(t('Assumption notes / recovery basis'),
                                        value=st.session_state.get(prefix+'notes', ''), key=prefix+'notes')
    st.caption(t('Funding, capital and margin inputs are annual effective-rate budgets. Their sum is converted to a continuous discount rate before pricing.'))
    for column, key, label in [(a, 'expected_delay_days', 'Expected payment delay after due date (days)'),
                               (b, 'recovery_lag_days', 'Additional recovery delay after collection date (days)')]:
        assumptions[key] = column.number_input(t(label), min_value=0, max_value=36500,
                                               value=st.session_state.get(prefix+key, 0), step=1, key=prefix+key)
    with st.expander(t('Investor policy limits')):
        assumptions['max_rate_percent'] = st.number_input(t('Maximum annual continuous rate (%)'), min_value=0.0,
            max_value=100.0, value=st.session_state.get(prefix+'max_rate_percent', 100.0), step=1.0, key=prefix+'max_rate_percent')
        assumptions['max_data_age_days'] = st.number_input(t('Maximum risk-data age (days)'), min_value=0,
            max_value=36500, value=st.session_state.get(prefix+'max_data_age_days', 365), step=1, key=prefix+'max_data_age_days')
    if origin == 'Illustrative assumptions':
        st.warning(t('Fictional inputs: this quote is a demonstration, not a calibrated credit assessment.'))
    else:
        st.caption(t('User-provided data are recorded with their source; the application has not independently verified them.'))
    if any(assumptions[key] is None for key, *_ in fields) or not source.strip():
        st.info(t('Complete risk inputs and their source, or explicitly load the fictional example.'))
        return None
    try:
        report = price_invoice(invoice, assumptions)
    except ValueError as exc:
        st.error(t(str(exc)))
        return None
    a, b, c = st.columns(3)
    a.metric(t('Model maximum advance'), euro(report['advance']) if report['advance'] else t('Not available'))
    b.metric(t('Calculated annual continuous rate (%)'), f"{report['annual_rate_percent']:.4f}" if report['annual_rate_percent'] is not None else '—')
    c.metric(t('Default probability over funding horizon (%)'), f"{100*report['horizon_pd']:.4f}")
    st.caption(t('Expected collection: {date} · Funding horizon: {days} days.',
                 date=report['expected_payment_on'], days=report['horizon_days']))
    st.caption(t('The advance is solved from expected discounted cash flows. The annual rate then connects that advance to full invoice repayment at the expected collection date.'))
    st.dataframe(pd.DataFrame([
        {t('Component'): t('Expected performing-payment PV'), t('Amount (€)'): report['survival_payment_pv']},
        {t('Component'): t('Expected recovery PV'), t('Amount (€)'): report['recovery_pv']},
        {t('Component'): t('Capital advanced'), t('Amount (€)'): report['advance']},
        {t('Component'): t('Upfront transaction costs (€)'), t('Amount (€)'): report['assumptions']['upfront_cost']},
        {t('Component'): t('Expected NPV after target return'), t('Amount (€)'): report['expected_npv']},
        {t('Component'): t('Expected principal credit loss, undiscounted'), t('Amount (€)'): report['expected_credit_loss']},
    ]), hide_index=True, use_container_width=True)
    for reason in report['blockers']:
        st.error(t(reason))
    with st.expander(t('Sensitivity to less favourable assumptions')):
        rows = stress_scenarios(invoice, assumptions)
        st.dataframe(pd.DataFrame([{
            t('Scenario'): t(row['scenario']), t('Model maximum advance'): row['advance'],
            t('Calculated annual continuous rate (%)'): row['annual_rate_percent'],
            t('Expected NPV at original proposed advance'): row['npv_at_base_advance'],
            t('Within policy'): t('Yes') if row['acceptable'] else t('No'),
        } for row in rows]), hide_index=True, use_container_width=True)
        st.caption(t('Mechanical sensitivities, not calibrated stress forecasts. Correlation and portfolio concentration are not modelled.'))
    with st.expander(t('Model assumptions and audit report')):
        st.caption(t('Constant default intensity; one collection date; default recoveries paid after that date plus the stated lag. Costs and capital/margin charges are explicit assumptions, not regulatory capital calculations.'))
        st.caption(t('PD is a real-world input for expected cash flows. The calculated rate is a cost-and-risk pricing proposal, not a market fair-value quote or a guaranteed return.'))
        st.code(report['model_version'] + '\n' + report['snapshot_hash'])
        st.download_button(t('Download pricing assumptions and calculation (JSON)'),
                           json.dumps(report, ensure_ascii=False, indent=2),
                           'pricing_' + invoice['id'] + '.json', 'application/json', key=prefix+'download')
    return report
