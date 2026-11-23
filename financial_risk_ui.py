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
    st.caption(t('Accounts closed on {date} · source: {filename}',
                 date=result['period_end'],filename=result['document']['filename']))
    st.caption(t('Manually entered figures; the document authenticity and company identity are not independently verified.'))
    st.caption(t('Published accounting indicator, not a default probability or a validated French SME credit rating. Rates follow a separate commercial tariff.'))
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


def render_accounts(invoice, store, t, *, save_accounts=save_buyer_accounts,
                    load_document=statement_document, company_mode=False):
    from accounting_extraction import apply_accounts_upload, restore_saved_accounts
    from accounting_dates import latest_accounts_check
    from hashlib import sha256
    from copy import deepcopy
    st.header(t('Buyer annual accounts'))
    st.write(t('Company annual accounts: {buyer}' if company_mode else 'Assess the company that owes the invoice: {buyer}',buyer=invoice['buyer']))
    st.caption(t('The PDF is read locally, with OCR for scanned pages. Prefilled figures are proposals to review, not authenticated financial data.'))
    st.caption(t('Documents are shared across app visitors. Upload only documents you are allowed to share.'))
    previous=invoice.get('buyer_accounts',{})
    archived=load_document(store,invoice)
    if archived:
        st.download_button(t('Download source annual accounts'),archived,
            file_name=previous['document']['filename'],mime='application/pdf',key='accounts_source_'+invoice['id'])
    if invoice.get('financing') or invoice['status']=='Closed':
        risk_summary(invoice,t)
        st.info(t('Historical financed operations are read-only. Their original amounts and pricing assumptions are preserved.'))
        return
    prefix='accounts_'+invoice['id']+'_'
    document=st.file_uploader(t('Buyer balance sheet and income statement · PDF · 5 MB max'),type=['pdf'],key=prefix+'pdf')
    st.caption(t('Attach both statements in one PDF. Recognised values and the provisional Z score update automatically; ambiguous fields stay empty.'))
    if document is not None:
        with st.spinner(t('Reading the annual accounts…')):
            apply_accounts_upload(st.session_state,prefix,document.getvalue())
        extracted=st.session_state.get(prefix+'extraction',{})
        count=len(extracted.get('values',{}))
        st.info(t('{count} accounting fields prefilled. Review the source lines and complete missing values.',count=count))
        for warning in extracted.get('warnings',[]):st.warning(t(warning))
        if extracted.get('used_ocr'):st.caption(t('OCR was used. Check digits, minus signs, units and comparative columns carefully.'))
        with st.expander(t('Detected values and document evidence')):
            st.json({key:({k:(v.isoformat() if isinstance(v,date) else v) for k,v in value.items()} if key=='fields' else value)
                     for key,value in extracted.items() if key in ('fields','values','evidence')})
    else:
        restore_saved_accounts(st.session_state,prefix,previous)
    def draft(name,default=None):return st.session_state.get(prefix+name,default)
    entity=st.text_input(t('Company named in the accounts'),value=draft('entity',previous.get('entity_name',invoice['buyer'])),key=prefix+'entity')
    siren=st.text_input(t('Buyer SIREN · format check only'),value=draft('siren',previous.get('buyer_siren','')),max_chars=9,key=prefix+'siren')
    kinds=['Choose company scope','Non-financial, non-manufacturing company','Other / model not applicable']
    kind=st.selectbox(t('Model applicability'),kinds,format_func=t,
        index=1 if previous.get('company_type')=='non_financial_non_manufacturing' else 0,key=prefix+'type')
    a,b=st.columns(2)
    start=a.date_input(t('Financial year start'),value=draft('start',date.fromisoformat(previous['period_start']) if previous else None),key=prefix+'start')
    end=b.date_input(t('Financial year end'),value=draft('end',date.fromisoformat(previous['period_end']) if previous else None),key=prefix+'end')
    freshness=None
    if end:
        freshness=latest_accounts_check(end)
        if freshness['status']=='future':st.error(t('The statement closing date is in the future.'))
        else:
            st.caption(t('Latest completed year end expected from this closing calendar: {date}',date=freshness['latest_completed']))
            if freshness['status']=='obsolete':
                st.error(t('These accounts are older than the expected latest annual period. Provide newer accounts or request manual review; age alone does not establish fraud.'))
            elif freshness['status']=='previous_in_preparation_window':
                st.warning(t('A newer financial year has ended, but its accounts may still be in preparation. The six-month V1 window is indicative, not a legal deadline.'))
            else:st.success(t('The closing date matches the latest completed period under this calendar check.'))
        st.caption(t('The fiscal closing calendar is inferred from the document. Without an external filing lookup, this does not prove these are the latest accounts available or detect fraud.'))
    reference=st.text_input(t('Statement source and page references'),value=draft('reference',previous.get('source_reference','')),key=prefix+'reference')
    st.caption(t('Enter EUR amounts, not thousands. Current liabilities include all amounts due within one year. Total liabilities include all non-equity liabilities, not only bank loans.'))
    st.caption(t('Retained earnings means accumulated undistributed profits/losses; exclude contributed capital and share premiums. EBIT is earnings before interest and tax, not EBITDA or net income. Ask the accountant to reconcile ambiguous lines.'))
    values={}
    for index,(key,label) in enumerate(FIELDS.items()):
        values[key]=(a if index%2==0 else b).number_input(t(label),value=draft(key,previous.get('values',{}).get(key)),step=100.0,
             min_value=0.0 if key in ('total_assets','current_assets','current_liabilities','total_liabilities') else None,key=prefix+key)
    extraction=deepcopy(st.session_state.get(prefix+'extraction') or previous.get('extraction'))
    if extraction:
        extraction['fields']={key:(value.isoformat() if isinstance(value,date) else value) for key,value in extraction.get('fields',{}).items()}
    reviewed=st.checkbox(t('I have reviewed the extracted figures, period and company against the PDF.'),
                         value=draft('reviewed',previous.get('extraction_reviewed',False)),key=prefix+'reviewed') if extraction else True
    accounts=dict(entity_name=entity,buyer_siren=siren,
        company_type='non_financial_non_manufacturing' if kind==kinds[1] else 'outside_scope',
        period_start=start.isoformat() if start else '',period_end=end.isoformat() if end else '',
        source_reference=reference,values=values)
    if extraction:accounts.update(extraction=extraction,extraction_reviewed=reviewed,latest_check=freshness)
    metadata=dict(filename=document.name,sha256=sha256(document.getvalue()).hexdigest()) if document else previous.get('document',{})
    preview=deepcopy(accounts);preview.update(document=metadata,extraction_reviewed=True)
    st.markdown('**'+t('Provisional accounting indicator — save reviewed data before financing')+'**')
    risk_summary(dict(invoice,buyer_accounts=preview),t)
    if not company_mode:
        with st.expander(t('Provisional tariff from these accounting figures')):
            from altman_tariff_ui import tariff_controls
            tariff_controls(dict(invoice,buyer_accounts=preview if metadata else None),t,lambda amount:f'{amount:,.2f} EUR')
    if st.button(t('Save accounting data and calculate'),type='primary',key=prefix+'save'):
        try:
            save_accounts(store,invoice,accounts,document.getvalue() if document else None,document.name if document else None)
            st.rerun()
        except ValueError as exc:st.error(t(str(exc)))
