"""Buyer accounting evidence and a transparent, published financial indicator."""
from datetime import date, timedelta
import pandas as pd
import streamlit as st
from financial_risk import FIELDS, SOURCE, REFERENCE, COEFFICIENTS, assess_buyer, save_buyer_accounts, statement_document


def risk_summary(invoice, t):
    result = assess_buyer(invoice)
    st.subheader(t('Buyer accounting risk'))
    if result['value'] is None:
        st.info(t('Risk not assessed'))
        st.caption(t(result['reason']))
        return result
    a,b = st.columns(2)
    a.metric(t('Altman Z-double-prime indicator'), f"{result['value']:.2f}")
    b.metric(t('Accounting risk zone'), t(result['band']))
    st.caption(t('Accounts closed on {date} · manually transcribed from {filename}',
                 date=result['period_end'],filename=result['document']['filename']))
    st.caption(t('Manually entered figures; the document authenticity and company identity are not independently verified.'))
    st.caption(t('Published model, not a default probability or a validated French SME credit rating. It does not determine an interest rate.'))
    with st.expander(t('Accounting inputs, formula and sources')):
        x,y,z=st.columns(3)
        x.metric(t('Current ratio'), f"{result['current_ratio']:.2f}" if result['current_ratio'] is not None else t('No current liabilities'))
        y.metric(t('Equity / total assets'), f"{result['equity_ratio_percent']:.2f} %")
        z.metric(t('EBIT / total assets'), f"{result['ebit_assets_percent']:.2f} %")
        st.latex(r'Z^{\prime\prime}=6.56X_1+3.26X_2+6.72X_3+1.05X_4')
        labels={'X1':'(Current assets - current liabilities) / total assets',
                'X2':'Retained earnings / total assets','X3':'EBIT / total assets',
                'X4':'Book equity / total liabilities'}
        st.dataframe(pd.DataFrame([{t('Ratio'): key,t('Calculation'):t(labels[key]),
            t('Value'):result['ratios'][key],t('Coefficient'):COEFFICIENTS[key],
            t('Contribution'):result['components'][key]} for key in labels]), hide_index=True)
        st.caption(t('Z below 1.10: distress zone. From 1.10 through 2.60: grey zone. Above 2.60: lower distress zone in the model, not a payment guarantee.'))
        st.dataframe(pd.DataFrame([{t('Accounting field'):t(FIELDS[k]),t('Amount (€)'):v}
            for k,v in invoice['buyer_accounts']['values'].items()]),hide_index=True)
        st.write(t('Source / provider / reference')+' : '+result['source_reference'])
        st.code(result['document']['sha256'])
        st.markdown('[Horváthová & Mokrišová (2018), §3.4]('+SOURCE+') · [NYU, appendix A]('+REFERENCE+')')
        st.caption(t('The V1 accepts annual accounts at most 548 days old. This is a freshness policy, not an Altman coefficient. No emerging-market +3.25 adjustment is applied.'))
    return result


def render_accounts(invoice, store, t):
    st.header(t('Buyer annual accounts'))
    st.write(t('Assess the company that owes the invoice: {buyer}',buyer=invoice['buyer']))
    st.caption(t('Use public or anonymised statements: this academic workspace is shared. Figures are entered manually from the PDF; no automatic accounting extraction or authenticity check is performed.'))
    risk_summary(invoice,t)
    previous=invoice.get('buyer_accounts',{})
    archived=statement_document(store,invoice)
    if archived:
        st.download_button(t('Download source annual accounts'),archived,
            file_name=previous['document']['filename'],mime='application/pdf',key='accounts_source_'+invoice['id'])
    if invoice.get('financing') or invoice['status']=='Closed':
        st.info(t('Historical financed operations are read-only. Their original amounts and pricing assumptions are preserved.'))
        return
    prefix='accounts_'+invoice['id']+'_'
    with st.form(prefix+'form'):
        document=st.file_uploader(t('Buyer balance sheet and income statement · PDF · 5 MB max'),type=['pdf'],key=prefix+'pdf')
        st.caption(t('Attach both statements in one PDF. Without them or with missing figures, no score is calculated.'))
        entity=st.text_input(t('Company named in the accounts'),value=previous.get('entity_name',invoice['buyer']),key=prefix+'entity')
        siren=st.text_input(t('Buyer SIREN · format check only'),value=previous.get('buyer_siren',''),max_chars=9,key=prefix+'siren')
        kinds=['Choose company scope','Non-financial, non-manufacturing company','Other / model not applicable']
        kind=st.selectbox(t('Model applicability'),kinds,format_func=t,
            index=1 if previous.get('company_type')=='non_financial_non_manufacturing' else 0,key=prefix+'type')
        a,b=st.columns(2)
        start=a.date_input(t('Financial year start'),value=date.fromisoformat(previous['period_start']) if previous else None,
                           max_value=date.today(),key=prefix+'start')
        end=b.date_input(t('Financial year end'),value=date.fromisoformat(previous['period_end']) if previous else None,
                         max_value=date.today(),key=prefix+'end')
        reference=st.text_input(t('Statement source and page references'),value=previous.get('source_reference',''),key=prefix+'reference')
        st.caption(t('Enter EUR amounts, not thousands. Current liabilities include all amounts due within one year. Total liabilities include all non-equity liabilities, not only bank loans.'))
        st.caption(t('Retained earnings means accumulated undistributed profits/losses; exclude contributed capital and share premiums. EBIT is earnings before interest and tax, not EBITDA or net income. Ask the accountant to reconcile ambiguous lines.'))
        values={}
        for index,(key,label) in enumerate(FIELDS.items()):
            values[key]=(a if index%2==0 else b).number_input(t(label),value=previous.get('values',{}).get(key),step=100.0,
                 min_value=0.0 if key in ('total_assets','current_assets','current_liabilities','total_liabilities') else None,key=prefix+key)
        save=st.form_submit_button(t('Save accounting data and calculate'),type='primary')
    if save:
        try:
            accounts=dict(entity_name=entity,buyer_siren=siren,
                company_type='non_financial_non_manufacturing' if kind==kinds[1] else 'outside_scope',
                period_start=start.isoformat() if start else '',period_end=end.isoformat() if end else '',
                source_reference=reference,values=values)
            save_buyer_accounts(store,invoice,accounts,document.getvalue() if document else None,document.name if document else None)
            st.rerun()
        except ValueError as exc:
            st.error(t(str(exc)))
