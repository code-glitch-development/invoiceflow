from datetime import date, timedelta
import json
import pandas as pd
import streamlit as st
from engine import seed, new_invoice, score, eligible, confirm, finance, quote, loss_scenario, settle

st.set_page_config(page_title='InvoiceFlow · Démonstrateur', page_icon='↗', layout='wide')
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

def euro(n):
    return f'{n:,.2f} €'.replace(',', ' ').replace('.', ',')

def table(items):
    return pd.DataFrame([{'Référence': i['reference'], 'PME': i['seller'], 'Client': i['buyer'],
        'Montant (€)': i['amount'], 'Échéance': i['due'], 'Statut': i['status'],
        'Score /100': score(i)[0], 'Suivi': i['outcome'] or '—'} for i in items])

def pick(items, key):
    return st.selectbox('Facture', [i['id'] for i in items], key=key,
        format_func=lambda value: next(f"{i['reference']} · {i['seller']} · {euro(i['amount'])}" for i in items if i['id'] == value))

def detail(i):
    a,b,c = st.columns(3)
    a.metric('Montant de la facture', euro(i['amount']))
    b.metric('Score pédagogique', f'{score(i)[0]} / 100')
    c.metric('Échéance', date.fromisoformat(i['due']).strftime('%d/%m/%Y'))
    with st.expander('Vérifications et traçabilité'):
        st.dataframe(pd.DataFrame([
            {'Contrôle': 'Identité PME', 'Résultat': 'Déclarée vérifiée (simulation)' if i['identity'] else 'À compléter'},
            {'Contrôle': 'Facture, commande, livraison', 'Résultat': 'Pièces déclarées complètes' if i['documents'] else 'À compléter'},
            {'Contrôle': 'Confirmation du client', 'Résultat': i['buyer_status']},
            {'Contrôle': 'Unicité dans la session', 'Résultat': 'Référence fournisseur et fichier contrôlés'},
            {'Contrôle': 'Risque pédagogique', 'Résultat': f"{score(i)[0]}/100 · seuil 65"},
        ]), hide_index=True, use_container_width=True)
        st.caption('Aucun contrôle officiel, OCR ou échange avec un client réel. Les cases du dépôt sont des déclarations de démonstration.')
        st.write('Empreinte SHA-256 des métadonnées')
        st.code(i['record_hash'])
        if i['file_hash']:
            st.write('Empreinte du fichier déposé')
            st.code(i['file_hash'])
        st.caption('Registre local à la session, sans blockchain. Une empreinte ne prouve ni la réalisation de la prestation, ni l’absence de cession sur une autre plateforme.')
        st.write('Barème du score')
        st.dataframe(pd.DataFrame([{'Critère': k, 'Points': v} for k,v in score(i)[1].items()]), hide_index=True)
        st.caption('Maximum 100 : solidité 40/25/5 ; historique 25/15/0 ; confirmation 25 ; pièces 10. Ce score ne constitue pas une probabilité de défaut.')
    if i['note']:
        st.info(i['note'])

with st.sidebar:
    st.title('InvoiceFlow ↗')
    st.caption('VERIFIED INVOICES. FASTER PAYMENTS.')
    profile = st.selectbox('Espace de démonstration', ['PME', 'Client final', 'Investisseur'])
    page = st.radio('Navigation', ['Vue d’ensemble', 'Déposer une facture', 'Validation client', 'Financement', 'Simulateur', 'Portefeuille'])
    st.divider()
    st.caption('Prototype pédagogique · NEOMA\n\nTous les acteurs et toutes les opérations sont fictifs. Aucun transfert d’argent.')
    with st.expander('Réinitialiser la démo'):
        reset = st.checkbox('Effacer les données de cette session')
        if st.button('Recharger les exemples', disabled=not reset):
            st.session_state.invoices = seed()
            st.rerun()

st.markdown('<div class="hero"><div class="eyebrow">INVOICEFLOW / DÉMO INTERACTIVE</div><h1>Vos factures. Votre trésorerie.</h1><p>Déposez, faites confirmer, simulez le financement.</p></div>', unsafe_allow_html=True)
st.caption(f'Espace {profile} · Profils librement interchangeables pour la démonstration, sans authentification. Les données restent dans la session courante et peuvent disparaître à sa fermeture.')
if 'notice' in st.session_state:
    st.success(st.session_state.pop('notice'))

if page == 'Vue d’ensemble':
    a,b,c,d = st.columns(4)
    a.metric('Volume déposé', euro(sum(i['amount'] for i in invoices)))
    b.metric('Factures à confirmer', sum(i['buyer_status']=='En attente' for i in invoices))
    c.metric('Éligibles à la simulation', sum(eligible(i) for i in invoices))
    d.metric('Avances simulées', euro(sum(i['financing']['advance'] for i in invoices if i['financing'])))
    st.subheader('Du dépôt au paiement anticipé')
    cols = st.columns(3)
    for col, title, body in zip(cols, ['01 · La PME dépose', '02 · Le client confirme', '03 · Le financeur décide'],
        ['Informations, pièces et contrôle des doublons.', 'Validation ou contestation de la prestation.', 'Score, commission et scénario de couverture.']):
        with col:
            st.markdown(f'**{title}**')
            st.write(body)
    st.subheader('Activité récente')
    st.dataframe(table(invoices), use_container_width=True, hide_index=True)
    st.info('Parcours conseillé : PME → dépôt ; Client final → validation ; Investisseur → financement ; Portefeuille → suivi du règlement.')

elif page == 'Déposer une facture':
    st.subheader('Libérez votre trésorerie')
    if profile != 'PME':
        st.info('Sélectionnez le profil PME pour déposer une facture.')
    else:
        with st.form('upload', clear_on_submit=False):
            a,b = st.columns(2)
            seller = a.text_input('Nom de la PME', placeholder='Ex. Atelier Nova')
            siren = b.text_input('SIREN · format de 9 chiffres', max_chars=9)
            buyer = a.text_input('Client final', placeholder='Ex. Groupe Horizon')
            reference = b.text_input('Référence de facture')
            amount = a.number_input('Montant de la facture (€)', min_value=1.0, value=10000.0, step=100.0)
            issued = b.date_input('Date d’émission', value=date.today(), max_value=date.today())
            due = a.date_input('Date d’échéance', value=date.today()+timedelta(days=60), min_value=date.today()+timedelta(days=1))
            strength = b.selectbox('Solidité déclarée du client', ['Solide', 'Intermédiaire', 'Fragile'])
            history = a.selectbox('Historique déclaré de paiement', ['Ponctuel', 'Retards occasionnels', 'Retards fréquents'])
            upload = st.file_uploader('Facture originale · PDF, PNG ou JPEG · 10 Mo max.', type=['pdf','png','jpg','jpeg'])
            st.caption('Facultatif pour la démo. Le fichier sert uniquement au calcul d’empreinte, sans lecture automatique. Utilisez des pièces fictives.')
            identity = st.checkbox('Simuler une identité PME vérifiée')
            documents = st.checkbox('Simuler un dossier complet : facture, bon de commande et preuve de livraison')
            submitted = st.form_submit_button('Déposer la facture', type='primary')
        if submitted:
            try:
                item = new_invoice(invoices, seller=seller, siren=siren.strip(), buyer=buyer, reference=reference,
                    amount=amount, issued=issued, due=due, documents=documents, identity=identity,
                    strength=strength, history=history, file_bytes=upload.getvalue() if upload else b'', filename=upload.name if upload else '')
                invoices.append(item)
                st.session_state.notice = f"Facture {item['reference']} déposée. Passez au profil Client final pour la confirmer."
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

elif page == 'Validation client':
    st.subheader('Confirmez les factures de vos fournisseurs')
    if profile != 'Client final':
        st.info('Sélectionnez le profil Client final pour confirmer ou contester une facture.')
    else:
        buyer = st.selectbox('Client représenté (simulation)', sorted({i['buyer'] for i in invoices}))
        items = [i for i in invoices if i['buyer']==buyer and i['status'] not in ('Financée','Clôturée')]
        if not items:
            st.info('Aucune facture à traiter pour ce client.')
        else:
            selected = pick(items, 'confirm_pick')
            i = next(i for i in items if i['id']==selected)
            detail(i)
            with st.form('confirm'):
                decision = st.radio('Décision', ['Confirmer', 'Contester'], horizontal=True)
                attestation = st.checkbox('Je simule la confirmation de la prestation, du montant, de l’échéance et de l’absence de règlement ou litige.')
                note = st.text_area('Commentaire · obligatoire en cas de contestation')
                submit = st.form_submit_button('Enregistrer la décision', type='primary')
            if submit:
                try:
                    if decision=='Confirmer' and not attestation:
                        raise ValueError('Cochez la confirmation des informations pour valider.')
                    confirm(i, decision=='Confirmer', note)
                    st.session_state.notice = 'Décision enregistrée.'
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

elif page == 'Financement':
    st.subheader('Financez des factures confirmées')
    if profile != 'Investisseur':
        st.info('Sélectionnez le profil Investisseur pour simuler un financement.')
    else:
        items = [i for i in invoices if i['status'] not in ('Financée','Clôturée')]
        if not items:
            st.info('Aucune facture disponible.')
        else:
            selected = pick(items, 'finance_pick')
            i = next(i for i in items if i['id']==selected)
            detail(i)
            st.caption('Conditions de la démo : confirmation client, identité et pièces déclarées vérifiées, échéance future et score ≥ 65/100.')
            rate = st.slider('Commission sur le montant nominal (%)', 0.0, 10.0, 4.0, .1)
            recourse = st.toggle('Avec recours contre la PME', value=False)
            coverage = st.slider('Couverture théorique de l’insolvabilité (% du nominal)', 0, 100, 80)
            q = quote(i['amount'], rate)
            a,b = st.columns(2)
            a.metric('Avance simulée à la PME', euro(q['advance']))
            b.metric('Marge brute si règlement intégral', euro(q['fee']))
            st.caption('Avant coût du capital, assurance, pertes et frais opérationnels. La couverture est une hypothèse et aucun assureur n’est connecté.')
            if not eligible(i):
                st.warning('Conditions non remplies : financement indisponible pour cette facture.')
            if st.button('Simuler le financement', type='primary', disabled=not eligible(i)):
                try:
                    finance(i, rate, recourse, coverage)
                    st.session_state.notice = 'Financement simulé enregistré dans le portefeuille.'
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

elif page == 'Simulateur':
    st.subheader('Testez vos hypothèses de financement')
    a,b = st.columns(2)
    amount = a.number_input('Facture (€)', min_value=1.0, value=10000.0, step=100.0)
    rate = b.slider('Commission (%)', 0.0, 10.0, 4.0, .1)
    coverage = a.slider('Couverture théorique de l’insolvabilité (%)', 0, 100, 80)
    recourse = b.toggle('Avec recours', value=False)
    result = loss_scenario(amount, rate, coverage, recourse)
    x,y,z = st.columns(3)
    x.metric('Avance immédiate', euro(result['advance']))
    y.metric('Commission brute', euro(result['fee']))
    z.metric('Capital exposé après assurance', euro(result['residual']))
    st.dataframe(pd.DataFrame([
        {'Scénario': 'Paiement intégral', 'Conséquence dans le modèle': f"{euro(amount)} encaissés ; marge brute {euro(result['fee'])}."},
        {'Scénario': 'Retard', 'Conséquence dans le modèle': 'Pas de perte définitive calculée ; durée du financement prolongée.'},
        {'Scénario': 'Insolvabilité couverte', 'Conséquence dans le modèle': f"Indemnité hypothétique {euro(result['indemnity'])} ; capital résiduel {euro(result['residual'])}."},
        {'Scénario': 'Contestation / fraude', 'Conséquence dans le modèle': 'Couverture non supposée ; exposition pouvant atteindre la totalité de l’avance.'},
    ]), hide_index=True, use_container_width=True)
    if recourse:
        st.info(f"Hypothèse de recours : créance sur la PME de {euro(result['supplier_claim'])} après indemnisation. Son recouvrement reste incertain ; l’exposition n’est pas annulée.")
    st.caption('Hypothèses simplifiées : couverture appliquée au nominal, indemnité plafonnée à l’avance, aucun recouvrement, franchise, délai ou coût pris en compte. Le sans recours ne signifie pas une protection contre toute fraude ou contestation.')
    st.subheader('Simulation de chiffre d’affaires')
    count = st.number_input('Factures financées par mois', min_value=1, value=100, step=1)
    a,b = st.columns(2)
    a.metric('Commission mensuelle théorique', euro(count*result['fee']))
    b.metric('Commission annuelle théorique', euro(count*result['fee']*12))
    st.caption('À volume constant, avant toutes charges. Cette simulation ne constitue pas une prévision commerciale.')

elif page == 'Portefeuille':
    st.subheader('Suivi des factures et des opérations')
    statuses = st.multiselect('Filtrer les statuts', sorted({i['status'] for i in invoices}))
    items = [i for i in invoices if not statuses or i['status'] in statuses]
    st.dataframe(table(items), hide_index=True, use_container_width=True)
    st.download_button('Exporter la vue en CSV', table(items).to_csv(index=False).encode('utf-8-sig'), 'invoiceflow_factures.csv', 'text/csv')
    st.download_button('Exporter la session en JSON', json.dumps(invoices, ensure_ascii=False, indent=2), 'invoiceflow_session.json', 'application/json')
    financed = [i for i in invoices if i['financing']]
    if financed:
        selected = pick(financed, 'portfolio_pick')
        i = next(i for i in financed if i['id']==selected)
        detail(i)
        f = i['financing']
        st.write(f"Avance : **{euro(f['advance'])}** · Commission : **{f['rate']} %** · Couverture hypothétique : **{f['coverage']} %** · {'Avec recours' if f['recourse'] else 'Sans recours'}")
        if i['outcome'] == 'Insolvabilité':
            r = loss_scenario(i['amount'], f['rate'], f['coverage'], f['recourse'])
            st.warning(f"Scénario d’insolvabilité : indemnité théorique {euro(r['indemnity'])}, capital restant exposé {euro(r['residual'])}. Aucun paiement réel.")
        elif i['outcome'] == 'Litige':
            st.warning(f"Litige : aucune indemnité supposée. Capital exposé : {euro(f['advance'])}.")
        elif i['outcome'] == 'Retard':
            st.info('Règlement en attente. Aucun revenu encaissé ni indemnisation automatique supposés.')
        elif i['outcome'] == 'Payée':
            st.success(f"Règlement intégral simulé. Marge brute théorique : {euro(f['fee'])}.")
        if profile == 'Investisseur' and i['status']=='Financée':
            with st.form('settle'):
                outcome = st.selectbox('Événement à simuler', ['Payée','Retard','Insolvabilité','Litige'])
                if st.form_submit_button('Enregistrer le suivi'):
                    settle(i, outcome)
                    st.session_state.notice = 'Suivi mis à jour.'
                    st.rerun()

st.divider()
st.caption('InvoiceFlow · Démonstrateur académique basé sur votre concept. Validation, score, assurance et financement simulés ; aucun service bancaire, registre externe ou blockchain connecté.')
