"""Investor opportunity cards, comparison and explicit batch simulation review."""
from datetime import date
from html import escape

import pandas as pd
import streamlit as st
from engine import buyer_outstanding_capital, canonical, money
from opportunities import (SCENARIOS, DEFAULT_COSTS, buyer_scenario, assumptions_for, opportunities,
                           filtered, review_selection, review_fingerprint)


def reset_filters():
    st.session_state.inv_budget = 25000.0
    st.session_state.inv_horizon = 90
    st.session_state.inv_scenario = 'All'


def toggle_selection(identifier):
    selected = list(st.session_state.get('investor_selection', []))
    if st.session_state['compare_' + identifier]:
        if identifier not in selected and len(selected) < 3:
            selected.append(identifier)
    elif identifier in selected:
        selected.remove(identifier)
    st.session_state.investor_selection = selected
    st.session_state.pop('investor_review', None)


def open_dossier(entry, navigate):
    invoice, report = entry['invoice'], entry['report']
    prefix = 'pricing_' + invoice['id'] + '_'
    for key, value in report['assumptions'].items():
        if key != 'pd_cohort':
            if key == 'source_date':
                value = date.fromisoformat(value)
            elif key in ('expected_delay_days', 'recovery_lag_days', 'max_data_age_days'):
                value = int(value)
            st.session_state[prefix + key] = value
    st.session_state[prefix + 'pd_mode'] = 'Internal fictional cohort'
    st.session_state[prefix + 'cohort_group'] = report['assumptions']['pd_cohort']['group']
    st.session_state.ui_pricing_method = 'Risk-based pricing'
    navigate('Investor', 'Financing', invoice)


def assumptions_page(invoices, t):
    st.header(t('Simulation assumptions'))
    st.info(t('Fictional borrower scenarios, not client credit ratings. The same buyer uses the same scenario across all opportunity cards.'))
    assignments = dict(st.session_state.get('investor_assignments', {}))
    buyers = {canonical(i['buyer']): i['buyer'] for i in invoices}
    for key, name in sorted(buyers.items()):
        assignments[key] = st.selectbox(name, list(SCENARIOS),
            index=list(SCENARIOS).index(buyer_scenario(name, assignments)),
            key='buyer_scenario_' + key, format_func=t)
        cohort = assumptions_for(assignments[key])['pd_cohort']
        st.caption(t('Fictional annual PD: {pd}% · {defaults} defaults / {buyers} buyers.',
            pd=f"{cohort['observed_pd_percent']:.2f}", defaults=cohort['defaults'], buyers=cohort['borrowers']))
    st.session_state.investor_assignments = assignments
    st.caption(t('PD comes from a separate fixed annual fictional cohort; adding invoice transactions does not dilute it.'))
    costs = dict(st.session_state.get('investor_costs', DEFAULT_COSTS))
    labels = {
        'lgd_percent': 'Nominal LGD before time discount (%)',
        'funding_rate_percent': 'Annual funding cost (%)',
        'capital_charge_percent': 'Annual capital charge (%)',
        'target_margin_percent': 'Annual target margin (%)',
        'upfront_cost': 'Upfront transaction costs (€)',
        'expected_delay_days': 'Expected payment delay after due date (days)',
        'recovery_lag_days': 'Additional recovery delay after collection date (days)',
        'max_rate_percent': 'Maximum annual continuous rate (%)',
        'max_data_age_days': 'Maximum risk-data age (days)',
    }
    for key, label in labels.items():
        value = costs[key]
        maximum = 36500 if isinstance(value, int) else (100.0 if key.endswith('percent') else 100000.0)
        costs[key] = st.number_input(t(label), min_value=0 if isinstance(value, int) else 0.0,
            max_value=maximum, value=value, key='investor_cost_' + key)
    st.session_state.investor_costs = costs
    st.caption(t('Changes reprice available opportunities only. Confirmed financing keeps its original assumptions.'))
    st.caption(t('LGD must reflect justified net recoveries. A coverage slider or recourse toggle alone does not establish a recovery value.'))


def comparison(chosen, portfolio, budget, t, euro):
    st.subheader(t('Compare your selection'))
    if not chosen:
        st.info(t('Select up to three invoices to compare them.'))
        return
    criteria = ['Buyer', 'Capital to advance', 'Payment horizon', 'Annual continuous rate (%)',
                'One-year buyer probability of default (%)', 'Nominal LGD before time discount (%)',
                'Full-payment proceeds', 'Potential gross gain', 'Existing buyer exposure']
    data = {t('Criterion'): [t(label) for label in criteria]}
    for entry in chosen:
        i, r = entry['invoice'], entry['report']
        data[i['reference']] = [i['buyer'], euro(r['advance']),
            t('{days} days', days=r['horizon_days']), f"{r['annual_rate_percent']:.2f}",
            f"{r['assumptions']['annual_pd_percent']:.2f}", f"{r['assumptions']['lgd_percent']:.1f}",
            euro(i['amount']), euro(r['gross_discount']),
            euro(buyer_outstanding_capital(portfolio, i['buyer'])['outstanding_capital'])]
    st.dataframe(pd.DataFrame(data), hide_index=True, use_container_width=True)
    # Sum selected advances by debtor, including multiple invoices for one debtor.
    grouped = {}
    for entry in chosen:
        i, r = entry['invoice'], entry['report']
        group = grouped.setdefault(canonical(i['buyer']), dict(buyer=i['buyer'], advance=0.0))
        group['advance'] += r['advance']
    st.markdown('**' + t('Buyer exposure after selection') + '**')
    for group in grouped.values():
        existing = buyer_outstanding_capital(portfolio, group['buyer'])['outstanding_capital']
        st.write(group['buyer'] + ' · ' + euro(existing + group['advance']))
    st.caption(t('Exposure uses buyer names in this demo, not verified legal identifiers.'))


def render_investor(page, invoices, database, t, euro, navigate):
    if page == 'Simulation assumptions':
        assumptions_page(invoices, t)
        return
    st.markdown('''<style>
    .investor-badge {display:inline-block;background:#dff4ec;color:#086b55;padding:6px 12px;border-radius:30px;font-size:.75rem;letter-spacing:.06em}
    [class*="st-key-offer_"] {background:white;border:1px solid #dce4ed;border-radius:16px;padding:20px}
    .offer-amount {font-size:1.85rem;font-weight:650;color:#13253c;margin:.6rem 0}
    .offer-buyer {color:#64748b;font-size:.9rem;margin-bottom:12px}
    .offer-scenario {border-radius:20px;padding:4px 10px;background:#eaf0f5;font-size:.8rem;display:inline-block}
    </style>''', unsafe_allow_html=True)
    st.markdown('<span class="investor-badge">' + escape(t('SIMULATION · FICTIONAL DATA')) + '</span>', unsafe_allow_html=True)
    st.title(t('Choose your next financing opportunities') if page == 'Overview' else t('Compare your selection'))
    st.caption(t('Compare capital, payment horizons and scenarios before simulating an investment.'))
    st.caption(t('Full invoices only. Gross gains assume full payment and are before costs; capital is at risk.'))
    st.session_state.setdefault('inv_budget', 25000.0)
    st.session_state.setdefault('inv_horizon', 90)
    st.session_state.setdefault('inv_scenario', 'All')
    with st.container(border=True):
        a, b, c, d = st.columns([1.2, 1.1, 1, 1])
        budget = a.number_input(t('Total budget (€)'), min_value=1.0, step=1000.0, key='inv_budget')
        horizon = b.selectbox(t('Maximum payment horizon'), [30, 60, 90, 180, 365, 36500],
            format_func=lambda days: t('{days} days', days=days), key='inv_horizon')
        scenario = c.selectbox(t('Scenario'), ['All'] + list(SCENARIOS), format_func=t, key='inv_scenario')
        d.button(t('Reset filters'), on_click=reset_filters, use_container_width=True)
    entries = opportunities(invoices, st.session_state.get('investor_assignments'), st.session_state.get('investor_costs'))
    available = {e['invoice']['id']: e for e in entries if e['report']['acceptable']}
    previous = st.session_state.get('investor_selection', [])
    selected = [identifier for identifier in previous if identifier in available]
    if selected != previous:
        st.warning(t('Unavailable invoices were removed from your selection.'))
        st.session_state.pop('investor_review', None)
    st.session_state.investor_selection = selected
    chosen = [available[identifier] for identifier in selected]
    visible = filtered(entries, budget, horizon, scenario)
    if page == 'Overview':
        st.subheader(t('Available opportunities') + f' · {len(visible)}')
        st.caption(t('Filters apply to each offer. Your total selection must also fit the budget.'))
        if not visible:
            st.info(t('No offers match these filters. Increase the budget or horizon, or reset the filters.'))
        if selected:
            selectors = ','.join('.st-key-offer_' + canonical(identifier) for identifier in selected)
            st.markdown('<style>' + selectors + '{border:2px solid #0d9f83;background:#fbfffd}</style>', unsafe_allow_html=True)
        columns = st.columns(3)
        for index, entry in enumerate(visible):
            invoice, report = entry['invoice'], entry['report']
            identifier = invoice['id']
            with columns[index % 3], st.container(border=False, key='offer_' + canonical(identifier)):
                st.session_state['compare_' + identifier] = identifier in selected
                st.checkbox(t('Compare'), key='compare_' + identifier,
                    disabled=len(selected) >= 3 and identifier not in selected,
                    on_change=toggle_selection, args=(identifier,))
                if identifier in selected:
                    st.caption('✓ ' + t('Selected'))
                st.markdown('<h3>' + escape(invoice['seller']) + '</h3>', unsafe_allow_html=True)
                st.markdown('<div class="offer-buyer">' + escape(t('Buyer')) + ' · ' + escape(invoice['buyer']) + '</div>' +
                    '<span class="offer-scenario">' + escape(t(entry['scenario'])) + '</span>' +
                    '<div class="offer-amount">' + escape(euro(report['advance'])) + '</div>', unsafe_allow_html=True)
                st.caption(t('Capital to advance'))
                st.write(t('Payment horizon') + ' · ' + t('{days} days', days=report['horizon_days']))
                st.caption(t('Expected payment') + ' · ' + report['expected_payment_on'])
                st.write(t('Full-payment proceeds') + ' · **' + euro(invoice['amount']) + '**')
                st.write(t('Potential gross gain') + ' · **' + euro(report['gross_discount']) + '**')
                outstanding = buyer_outstanding_capital(invoices, invoice['buyer'])['outstanding_capital']
                if outstanding:
                    st.warning(t('Already exposed to this buyer') + ' · ' + euro(outstanding))
                st.caption(invoice['reference'])
                st.button(t('View invoice details'), key='dossier_' + identifier,
                    on_click=open_dossier, args=(entry, navigate), use_container_width=True)
        with st.expander(t('Demo data and unavailable offers')):
            st.caption(t('Add two fictional eligible examples without replacing existing invoices.'))
            if st.button(t('Add investor examples'), key='investor_add_examples'):
                try:
                    database.add_examples()
                    st.rerun()
                except ValueError as exc:
                    st.error(t(str(exc)))
            for entry in entries:
                if not entry['report']['acceptable']:
                    st.write(entry['invoice']['reference'])
                    for reason in entry['report']['blockers']:
                        st.caption(t(reason))
    hidden = sum(identifier not in {e['invoice']['id'] for e in visible} for identifier in selected)
    if hidden:
        st.info(t('{count} selected invoices are hidden by your filters.', count=hidden))
    left, right = st.columns([2, 1])
    with left:
        comparison(chosen, invoices, budget, t, euro)
    with right, st.container(border=True):
        st.subheader(t('Your selection') + f' · {len(chosen)}/3')
        total = money(sum(e['report']['advance'] for e in chosen))
        st.metric(t('Total capital'), euro(total))
        st.metric(t('Potential gross gain'), euro(money(sum(e['report']['gross_discount'] for e in chosen))))
        st.caption(t('Remaining budget') + ' · ' + euro(budget - total))
        if total > budget:
            st.warning(t('The total advance exceeds your budget.'))
        if st.button(t('Simulate this selection'), key='review_selection', type='primary',
                     disabled=not chosen or total > budget, use_container_width=True):
            try:
                st.session_state.investor_review = review_selection(entries, selected, budget, invoices)
            except ValueError as exc:
                st.error(t(str(exc)))
    review = st.session_state.get('investor_review')
    if review:
        try:
            current = review_selection(entries, selected, budget, invoices)
            valid = review_fingerprint(current) == review_fingerprint(review)
        except ValueError:
            valid = False
        if not valid:
            st.session_state.pop('investor_review', None)
            st.warning(t('The selection changed. Review the latest offers before confirming.'))
        else:
            with st.container(border=True):
                st.subheader(t('Review before confirming'))
                for entry in review['rows']:
                    st.write(entry['invoice']['reference'] + ' · ' + euro(entry['report']['advance']) +
                             ' → ' + euro(entry['invoice']['amount']) + ' · ' + entry['report']['expected_payment_on'])
                st.write(t('Total capital') + ' · **' + euro(review['advance']) + '**')
                st.write(t('Full-payment proceeds') + ' · **' + euro(review['repayment']) + '**')
                st.caption(t('This records simulated financing only. No money is transferred. Full-payment proceeds are not guaranteed.'))
                if st.button(t('Confirm financing simulation'), key='confirm_selection', type='primary'):
                    try:
                        database.finance_selection(review)
                        st.session_state.investor_selection = []
                        st.session_state.pop('investor_review', None)
                        st.session_state.notice = t('Financing simulation saved. Follow payment in your portfolio.')
                        navigate('Investor', 'Portfolio')
                        st.rerun()
                    except ValueError as exc:
                        st.session_state.pop('investor_review', None)
                        st.error(t(str(exc)))
