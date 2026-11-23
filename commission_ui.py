"""Shared bilingual cash-flow breakdown for previews and saved transactions."""
import streamlit as st


def render_commission_breakdown(amount, funding, t, euro):
    # Historical operations without a recorded commission keep their original terms.
    if 'platform_commission' not in funding:
        return
    st.write('**' + t('SME cost breakdown') + '**')
    rows = [
        ('Invoice face value including tax', amount),
        ('Financing cost / gross investor gain', funding.get('gross_discount', funding.get('fee', 0))),
        ('InvoiceFlow commission (1% once)', funding['platform_commission']),
        ('Total cost to the SME', funding['total_sme_cost']),
        ('Net payment to the SME', funding['sme_net_proceeds']),
    ]
    st.table([{t('Component'): t(label), t('Amount (€)'): euro(value)} for label, value in rows])
    st.caption(t('The 1% commission is charged once on the invoice total including tax and deducted from the investor advance. It is platform revenue, separate from the investor gain. It is not an annual rate. Other charges and any tax on the commission are not modelled.'))
