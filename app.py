from datetime import date, timedelta
import json
import pandas as pd
import streamlit as st
from engine import seed, new_invoice, score, eligible, confirm, finance, quote, loss_scenario, settle, migrate_session

st.set_page_config(page_title='InvoiceFlow · Demo', page_icon='↗', layout='wide')
st.markdown('''<style>
.block-container {padding-top:2rem; max-width:1400px}
[data-testid="stSidebar"] {background:#13253c}
[data-testid="stSidebar"] * {color:#f2f6fb}
[data-testid="stSidebar"] [data-baseweb="select"] * {color:#142239}
[data-testid="stMetric"] {background:white; border:1px solid #e1e8ef; padding:20px; border-radius:16px}
.hero {background:linear-gradient(120deg,#13253c,#164b53);color:white;padding:32px;border-radius:22px;margin-bottom:24px}
.hero h1 {color:white;font-size:2.6rem;margin:0}.hero p {color:#d3e7e6;margin-bottom:0}
.eyebrow {font-size:.8rem;letter-spacing:.16em;color:#87e3c7;margin-bottom:10px}
</style>''', unsafe_allow_html=True)
if 'invoices' not in st.session_state:
    st.session_state.invoices = seed()
invoices = st.session_state.invoices
migrate_session(invoices)

def euro(n):
    return f'€{n:,.2f}'

def table(items):
    return pd.DataFrame([{'Reference': i['reference'], 'SME': i['seller'], 'Buyer': i['buyer'],
        'Amount (€)': i['amount'], 'Due date': i['due'], 'Status': i['status'],
        'Score /100': score(i)[0], 'Tracking': i['outcome'] or '—'} for i in items])

def pick(items, key):
    return st.selectbox('Invoice', [i['id'] for i in items], key=key,
        format_func=lambda value: next(f"{i['reference']} · {i['seller']} · {euro(i['amount'])}" for i in items if i['id'] == value))

def detail(i):
    a,b,c = st.columns(3)
    a.metric('Invoice amount', euro(i['amount']))
    b.metric('Demo score', f'{score(i)[0]} / 100')
    c.metric('Due date', date.fromisoformat(i['due']).strftime('%d %b %Y'))
    with st.expander('Checks and audit trail'):
        st.dataframe(pd.DataFrame([
            {'Check': 'SME identity', 'Result': 'Declared verified (simulation)' if i['identity'] else 'Incomplete'},
            {'Check': 'Invoice, purchase order, delivery', 'Result': 'Documents declared complete' if i['documents'] else 'Incomplete'},
            {'Check': 'Buyer confirmation', 'Result': i['buyer_status']},
            {'Check': 'Uniqueness within this session', 'Result': 'Supplier reference and file checked'},
            {'Check': 'Demo risk assessment', 'Result': f"{score(i)[0]}/100 · threshold 65"},
        ]), hide_index=True, use_container_width=True)
        st.caption('No official checks, OCR or contact with a real buyer. The upload checkboxes are demo declarations.')
        st.write('SHA-256 fingerprint of metadata')
        st.code(i['record_hash'])
        if i['file_hash']:
            st.write('Uploaded file fingerprint')
            st.code(i['file_hash'])
        st.caption('Session-local register, without blockchain. A fingerprint proves neither delivery of the service nor the absence of assignment on another platform.')
        st.write('Score breakdown')
        st.dataframe(pd.DataFrame([{'Criterion': k, 'Points': v} for k,v in score(i)[1].items()]), hide_index=True)
        st.caption('Maximum 100: financial strength 40/25/5; payment history 25/15/0; confirmation 25; documents 10. This score is not a probability of default.')
    if i['note']:
        st.info(i['note'])

with st.sidebar:
    st.title('InvoiceFlow ↗')
    st.caption('VERIFIED INVOICES. FASTER PAYMENTS.')
    profile = st.selectbox('Demo role', ['SME', 'Buyer', 'Investor'])
    page = st.radio('Navigation', ['Overview', 'Upload an invoice', 'Buyer confirmation', 'Financing', 'Simulator', 'Portfolio'])
    st.divider()
    st.caption('Educational prototype · NEOMA\n\nAll parties and transactions are fictional. No money is transferred.')
    with st.expander('Reset demo'):
        reset = st.checkbox('Clear the data in this session')
        if st.button('Reload examples', disabled=not reset):
            st.session_state.invoices = seed()
            st.rerun()

st.markdown('<div class="hero"><div class="eyebrow">INVOICEFLOW / INTERACTIVE DEMO</div><h1>Your invoices. Your cash flow.</h1><p>Upload, confirm and simulate financing.</p></div>', unsafe_allow_html=True)
st.caption(f'{profile} workspace · Switch roles freely for the demo; there is no authentication. Data stays in the current session and may be lost when it ends.')
if 'notice' in st.session_state:
    st.success(st.session_state.pop('notice'))

if page == 'Overview':
    a,b,c,d = st.columns(4)
    a.metric('Submitted volume', euro(sum(i['amount'] for i in invoices)))
    b.metric('Invoices awaiting confirmation', sum(i['buyer_status']=='Pending' for i in invoices))
    c.metric('Eligible for financing simulation', sum(eligible(i) for i in invoices))
    d.metric('Simulated advances', euro(sum(i['financing']['advance'] for i in invoices if i['financing'])))
    st.subheader('From upload to early payment')
    cols = st.columns(3)
    for col, title, body in zip(cols, ['01 · The SME uploads', '02 · The buyer confirms', '03 · The investor decides'],
        ['Details, documents and duplicate checks.', 'Confirm or dispute the service.', 'Score, fee and coverage scenario.']):
        with col:
            st.markdown(f'**{title}**')
            st.write(body)
    st.subheader('Recent activity')
    st.dataframe(table(invoices), use_container_width=True, hide_index=True)
    st.info('Suggested journey: SME → upload; Buyer → confirmation; Investor → financing; Portfolio → payment tracking.')

elif page == 'Upload an invoice':
    st.subheader('Unlock your cash flow')
    if profile != 'SME':
        st.info('Select the SME role to upload an invoice.')
    else:
        with st.form('upload', clear_on_submit=False):
            a,b = st.columns(2)
            seller = a.text_input('SME name', placeholder='E.g. Atelier Nova')
            siren = b.text_input('SIREN · 9-digit format', max_chars=9)
            buyer = a.text_input('Buyer', placeholder='E.g. Groupe Horizon')
            reference = b.text_input('Invoice reference')
            amount = a.number_input('Invoice amount (€)', min_value=1.0, value=10000.0, step=100.0)
            issued = b.date_input('Issue date', value=date.today(), max_value=date.today())
            due = a.date_input('Due date', value=date.today()+timedelta(days=60), min_value=date.today()+timedelta(days=1))
            strength = b.selectbox('Declared buyer financial strength', ['Strong', 'Average', 'Weak'])
            history = a.selectbox('Declared payment history', ['On time', 'Occasional delays', 'Frequent delays'])
            upload = st.file_uploader('Original invoice · PDF, PNG or JPEG · 10 MB max.', type=['pdf','png','jpg','jpeg'])
            st.caption('Optional for the demo. The file is only used to calculate a fingerprint, without automatic extraction. Use fictional documents.')
            identity = st.checkbox('Simulate verified SME identity')
            documents = st.checkbox('Simulate complete documentation: invoice, purchase order and proof of delivery')
            submitted = st.form_submit_button('Submit invoice', type='primary')
        if submitted:
            try:
                item = new_invoice(invoices, seller=seller, siren=siren.strip(), buyer=buyer, reference=reference,
                    amount=amount, issued=issued, due=due, documents=documents, identity=identity,
                    strength=strength, history=history, file_bytes=upload.getvalue() if upload else b'', filename=upload.name if upload else '')
                invoices.append(item)
                st.session_state.notice = f"Invoice {item['reference']} submitted. Switch to the Buyer role to confirm it."
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

elif page == 'Buyer confirmation':
    st.subheader('Confirm your supplier invoices')
    if profile != 'Buyer':
        st.info('Select the Buyer role to confirm or dispute an invoice.')
    else:
        buyer = st.selectbox('Represented buyer (simulation)', sorted({i['buyer'] for i in invoices}))
        items = [i for i in invoices if i['buyer']==buyer and i['status'] not in ('Financed','Closed')]
        if not items:
            st.info('No invoices to process for this buyer.')
        else:
            selected = pick(items, 'confirm_pick')
            i = next(i for i in items if i['id']==selected)
            detail(i)
            with st.form('confirm'):
                decision = st.radio('Decision', ['Confirm', 'Dispute'], horizontal=True)
                attestation = st.checkbox('I simulate confirmation of the service, amount and due date, and that the invoice is unpaid and undisputed.')
                note = st.text_area('Comment · required for a dispute')
                submit = st.form_submit_button('Save decision', type='primary')
            if submit:
                try:
                    if decision=='Confirm' and not attestation:
                        raise ValueError('Check the confirmation box to approve the invoice.')
                    confirm(i, decision=='Confirm', note)
                    st.session_state.notice = 'Decision saved.'
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

elif page == 'Financing':
    st.subheader('Finance confirmed invoices')
    if profile != 'Investor':
        st.info('Select the Investor role to simulate financing.')
    else:
        items = [i for i in invoices if i['status'] not in ('Financed','Closed')]
        if not items:
            st.info('No invoices available.')
        else:
            selected = pick(items, 'finance_pick')
            i = next(i for i in items if i['id']==selected)
            detail(i)
            st.caption('Demo requirements: buyer confirmation, identity and documents declared verified, a future due date and a score ≥ 65/100.')
            rate = st.slider('Fee on face value (%)', 0.0, 10.0, 4.0, .1)
            recourse = st.toggle('With recourse to the SME', value=False)
            coverage = st.slider('Hypothetical insolvency coverage (% of face value)', 0, 100, 80)
            q = quote(i['amount'], rate)
            a,b = st.columns(2)
            a.metric('Simulated advance to the SME', euro(q['advance']))
            b.metric('Gross margin if paid in full', euro(q['fee']))
            st.caption('Before capital costs, insurance, losses and operating expenses. Coverage is hypothetical; no insurer is connected.')
            if not eligible(i):
                st.warning('Requirements not met: financing is unavailable for this invoice.')
            if st.button('Simulate financing', type='primary', disabled=not eligible(i)):
                try:
                    finance(i, rate, recourse, coverage)
                    st.session_state.notice = 'Simulated financing saved to the portfolio.'
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

elif page == 'Simulator':
    st.subheader('Explore financing scenarios')
    a,b = st.columns(2)
    amount = a.number_input('Invoice (€)', min_value=1.0, value=10000.0, step=100.0)
    rate = b.slider('Fee (%)', 0.0, 10.0, 4.0, .1)
    coverage = a.slider('Hypothetical insolvency coverage (%)', 0, 100, 80)
    recourse = b.toggle('With recourse', value=False)
    result = loss_scenario(amount, rate, coverage, recourse)
    x,y,z = st.columns(3)
    x.metric('Immediate advance', euro(result['advance']))
    y.metric('Gross fee', euro(result['fee']))
    z.metric('Capital at risk after insurance', euro(result['residual']))
    st.dataframe(pd.DataFrame([
        {'Scenario': 'Full payment', 'Model outcome': f"{euro(amount)} received; gross margin {euro(result['fee'])}."},
        {'Scenario': 'Late payment', 'Model outcome': 'No final loss calculated; financing period extended.'},
        {'Scenario': 'Covered insolvency', 'Model outcome': f"Hypothetical indemnity {euro(result['indemnity'])} ; residual capital {euro(result['residual'])}."},
        {'Scenario': 'Dispute / fraud', 'Model outcome': 'No coverage assumed; exposure may reach the full advance.'},
    ]), hide_index=True, use_container_width=True)
    if recourse:
        st.info(f"Recourse assumption: a claim against the SME for {euro(result['supplier_claim'])} after indemnification. Recovery remains uncertain; the exposure is not eliminated.")
    st.caption('Simplified assumptions: coverage applied to face value, indemnity capped at the advance; no recoveries, deductibles, delays or costs included. Non-recourse does not mean protection against every fraud or dispute.')
    st.subheader('Revenue simulation')
    count = st.number_input('Invoices financed per month', min_value=1, value=100, step=1)
    a,b = st.columns(2)
    a.metric('Hypothetical monthly fee revenue', euro(count*result['fee']))
    b.metric('Hypothetical annual fee revenue', euro(count*result['fee']*12))
    st.caption('At constant volume, before all expenses. This simulation is not a business forecast.')

elif page == 'Portfolio':
    st.subheader('Invoice and transaction tracking')
    statuses = st.multiselect('Filter statuses', sorted({i['status'] for i in invoices}))
    items = [i for i in invoices if not statuses or i['status'] in statuses]
    st.dataframe(table(items), hide_index=True, use_container_width=True)
    st.download_button('Export view as CSV', table(items).to_csv(index=False).encode('utf-8-sig'), 'invoiceflow_invoices.csv', 'text/csv')
    st.download_button('Export session as JSON', json.dumps(invoices, ensure_ascii=False, indent=2), 'invoiceflow_session.json', 'application/json')
    financed = [i for i in invoices if i['financing']]
    if financed:
        selected = pick(financed, 'portfolio_pick')
        i = next(i for i in financed if i['id']==selected)
        detail(i)
        f = i['financing']
        st.write(f"Advance: **{euro(f['advance'])}** · Fee: **{f['rate']} %** · Hypothetical coverage: **{f['coverage']} %** · {'With recourse' if f['recourse'] else 'Without recourse'}")
        if i['outcome'] == 'Insolvency':
            r = loss_scenario(i['amount'], f['rate'], f['coverage'], f['recourse'])
            st.warning(f"Insolvency scenario: hypothetical indemnity {euro(r['indemnity'])}, remaining capital at risk {euro(r['residual'])}. No real payment.")
        elif i['outcome'] == 'Dispute':
            st.warning(f"Dispute: no indemnity assumed. Capital at risk: {euro(f['advance'])}.")
        elif i['outcome'] == 'Late payment':
            st.info('Payment pending. No collected revenue or automatic indemnity assumed.')
        elif i['outcome'] == 'Paid':
            st.success(f"Full payment simulated. Hypothetical gross margin: {euro(f['fee'])}.")
        if profile == 'Investor' and i['status']=='Financed':
            with st.form('settle'):
                outcome = st.selectbox('Event to simulate', ['Paid','Late payment','Insolvency','Dispute'])
                if st.form_submit_button('Save tracking update'):
                    settle(i, outcome)
                    st.session_state.notice = 'Tracking updated.'
                    st.rerun()

st.divider()
st.caption('InvoiceFlow · Academic demo based on your concept. Confirmation, scoring, insurance and financing are simulated; no banking service, external register or blockchain is connected.')
