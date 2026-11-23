"""Explicit commercial tariff controls, distinct from a calibrated default-risk model."""
import streamlit as st
from altman_tariff import POLICY,tariff_quote
from portfolio import holding_yield_percent


def tariff_controls(invoice,t,euro):
    st.subheader(t('Z-linked commercial tariff — demonstration'))
    st.caption(t('This tariff is a commercial hypothesis: 5% base, +2 points in the grey zone, +4 points in distress, +5 points without accounts. It is not an Altman-derived probability of default.'))
    try:
        report=tariff_quote(invoice)
    except ValueError as exc:
        st.error(t(str(exc)))
        return dict(acceptable=False,blockers=[str(exc)])
    a,b,c=st.columns(3)
    a.metric(t('Annual continuous tariff'),f"{report['policy_annual_rate_percent']:.2f} %")
    b.metric(t('Additional tariff premium'),f"+{report['risk_premium_pp']:.2f} "+t('percentage points'))
    c.metric(t('Buyer accounting risk'),t(report['accounting_status']))
    if report['accounting_z'] is None:
        st.warning(t('The buyer risk is not assessed. The 10% rate is an information-uncertainty surcharge, not proof that the risk is covered.'))
    a,b,c=st.columns(3)
    a.metric(t('Simulated advance to the SME'),euro(report['advance']))
    b.metric(t('Potential gross gain'),euro(report['gross_discount']))
    c.metric(t('Payment horizon'),t('{days} days',days=report['horizon_days']))
    st.write(t('Gross return over the operation')+f" · **{holding_yield_percent(invoice['amount'],report['advance']):.2f} %**")
    st.latex(r'PV=FV\,e^{-r\,d/365}')
    st.caption(t('The invoice face value is FV. The tariff is annual and continuous; the actual days to maturity determine the advance. Rounding is to cents. Returns assume full payment and exclude costs and losses.'))
    for reason in report['blockers']:st.error(t(reason))
    with st.expander(t('Tariff calculation details')):st.json(report)
    return report
