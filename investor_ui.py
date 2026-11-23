"""Investor opportunity cards, comparison and explicit batch simulation review."""
from datetime import date
from html import escape

import pandas as pd
import streamlit as st
from engine import buyer_outstanding_capital, canonical, money
from portfolio import holding_yield_percent, portfolio_summary
from financial_risk import assess_buyer
from pricing_ui import illustrative_pricing_consent
from opportunities import (SCENARIOS, DEFAULT_COSTS, buyer_scenario, assumptions_for, opportunities, tariff_opportunities,
                           filtered, review_selection, review_fingerprint)


# These are the existing fictional scenarios, not PD thresholds or credit ratings.
RISK_COLORS = {
    'Prudent': ('Prudent pricing scenario', '#166534', '#dcfce7'),
    'Central': ('Central pricing scenario', '#92400e', '#fef3c7'),
    'Stressed': ('Stressed pricing scenario', '#991b1b', '#fee2e2'),
    'Unknown': ('Risk not assessed', '#475569', '#f1f5f9'),
}


def risk_label(scenario, t):
    return t(RISK_COLORS[scenario][0]) + ' · ' + t(scenario)


def risk_badge(scenario, t):
    _, foreground, background = RISK_COLORS[scenario]
    return ('<span class="offer-scenario" style="color:' + foreground + ';background:' + background +
            '">' + escape(risk_label(scenario, t)) + '</span>')


def reset_filters():
    st.session_state.inv_budget = 25000.0
    st.session_state.inv_horizon = 90
    st.session_state.inv_scenario = 'All'
    st.session_state.investor_filters = dict(inv_budget=25000.0, inv_horizon=90, inv_scenario='All')


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
    if report['model_version']=='altman-tariff-demo-v1':
        st.session_state.ui_pricing_method='Z-linked tariff (demo)'
        navigate('Investor','Financing',invoice)
        return
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
    st.session_state.ui_with_recourse_to_the_sme = False
    st.session_state.ui_hypothetical_insolvency_coverage_of_face_value = 0
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
    criteria = ['Buyer', 'Pricing scenario', 'Capital to advance', 'Payment horizon', 'Gross annual yield (continuous, %)',
                'Gross return over the operation (%)',
                'One-year buyer probability of default (%)', 'Nominal LGD before time discount (%)',
                'Full-payment proceeds', 'Potential gross gain', 'Existing buyer exposure']
    data = {t('Criterion'): [t(label) for label in criteria]}
    for entry in chosen:
        i, r = entry['invoice'], entry['report']
        data[i['reference'] + ' · ' + i['id']] = [i['buyer'], risk_label(entry['scenario'], t), euro(r['advance']),
            t('{days} days', days=r['horizon_days']), f"{r['annual_rate_percent']:.2f}",
            f"{holding_yield_percent(i['amount'], r['advance']):.2f}",
            f"{r['assumptions']['annual_pd_percent']:.2f}" if 'annual_pd_percent' in r['assumptions'] else '—', f"{r['assumptions']['lgd_percent']:.1f}" if 'lgd_percent' in r['assumptions'] else '—',
            euro(i['amount']), euro(r['gross_discount']),
            euro(buyer_outstanding_capital(portfolio, i['buyer'])['outstanding_capital'])]
    frame = pd.DataFrame(data)
    styles = {risk_label(scenario, t): f'color: {foreground}; background-color: {background}; font-weight: 600'
              for scenario, (_, foreground, background) in RISK_COLORS.items()}
    styled = frame.style.apply(lambda column: column.map(lambda value: styles.get(value, '')),
                               subset=pd.IndexSlice[[1], frame.columns[1:]])
    st.dataframe(styled, hide_index=True, use_container_width=True)
    st.caption(t('Returns assume full payment on the expected payment date, before costs and losses. They are not guaranteed.'))
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


def render_portfolio_summary(invoices, t, euro, detailed=True):
    summary = portfolio_summary(invoices)
    st.subheader(t('Your investment portfolio'))
    percent = lambda value: '—' if value is None else f'{value:.2f} %'
    a, b, c = st.columns(3)
    a.metric(t('Outstanding capital'), euro(summary['outstanding_capital']))
    b.metric(t('Projected gross portfolio return'), percent(summary['projected_return_percent']))
    c.metric(t('Average annual rate on unpaid invoices'), percent(summary['weighted_annual_rate_percent']))
    st.caption(t('The global return includes paid and unpaid financed invoices, assuming full payment. It is a gross return over the operations, not an annual return.'))
    if summary['annual_missing_count']:
        st.info(t('Annual average unavailable: {count} unpaid invoices have missing or invalid financing dates.',
                  count=summary['annual_missing_count']))
    if summary['overdue_count']:
        st.warning(t('{count} overdue invoices · {capital} of unpaid capital.',
                     count=summary['overdue_count'], capital=euro(summary['overdue_capital'])))
    metrics = [
        ('Total capital advanced', euro(summary['total_capital_advanced'])),
        ('Projected total gross gain', euro(summary['projected_gross_gain'])),
        ('Realized gross return (simulation)', percent(summary['realized_return_percent'])),
        ('Simulated repayments received', euro(summary['repayments'])),
        ('Realized gross gains (simulation)', euro(summary['realized_gain'])),
        ('Potential gross gains on unpaid invoices', euro(summary['potential_gain'])),
        ('Capital on overdue invoices', euro(summary['overdue_capital'])),
        ('Overdue invoices', str(summary['overdue_count'])),
    ]
    with st.expander(t('Portfolio performance details')):
        for offset in range(0, len(metrics), 3):
            for column, (label, value) in zip(st.columns(3), metrics[offset:offset + 3]):
                column.metric(t(label), value)
        st.caption(t('Global return = (realized gross gains + potential gross gains) / total capital advanced. Realized return uses only the capital and gains of paid invoices.'))
        st.caption(t('The annual indicator is a capital-weighted average of the original continuous rates on unpaid invoices. It is not a cash-flow IRR or a guaranteed return.'))
        st.caption(t('Annual rates are derived from the saved advance, full-payment proceeds, financing date and expected payment date (or due date in manual mode). Independent theoretical-interest settings are excluded.'))
    st.caption(t('Whole saved portfolio, independent of filters. Repayments include returned capital; realized gains are counted only after simulated full payment.'))
    st.caption(t('Gains are before costs and losses. Potential gains assume full payment of every unpaid financed invoice, including incidents. Theoretical interest and hypothetical insurance are excluded.'))
    if not detailed:
        return
    st.markdown('**' + t('Outstanding exposure by buyer') + '**')
    if summary['exposure']:
        st.dataframe(pd.DataFrame([{t('Buyer'): row['buyer'],
            t('Outstanding capital'): euro(row['capital']),
            t('Share of outstanding capital'): f"{row['share_percent']:.2f} %",
            t('Unpaid financed invoices'): row['count']} for row in summary['exposure']]),
            hide_index=True, use_container_width=True)
        st.caption(t('Exposure uses buyer names in this demo, not verified legal identifiers.'))
    else:
        st.info(t('No outstanding financed invoices.'))
    st.markdown('**' + t('Overdue invoice tracking') + '**')
    st.caption(t('An unpaid financed invoice is overdue after its due date or when a late-payment event is recorded. Due today is not overdue.'))
    if summary['overdue']:
        st.dataframe(pd.DataFrame([{t('Reference'): i['reference'], t('Buyer'): i['buyer'],
            t('Due date'): i['due'], t('Outstanding capital'): euro(i['financing']['advance']),
            t('Tracking'): t(i.get('outcome') or 'Late payment')} for i in summary['overdue']]),
            hide_index=True, use_container_width=True)
    else:
        st.info(t('No overdue financed invoices.'))


def render_investor(page, invoices, database, t, euro, navigate):
    if page == 'Simulation assumptions':
        assumptions_page(invoices, t)
        return
    st.markdown('''<style>
    .investor-badge {display:inline-block;background:#dff4ec;color:#086b55;padding:6px 12px;border-radius:30px;font-size:.75rem;letter-spacing:.06em}
    [class*="st-key-offer_"] {background:white;border:1px solid #dce4ed;border-radius:16px;padding:20px}
    .offer-amount {font-size:1.85rem;font-weight:650;color:#13253c;margin:.6rem 0}
    .offer-buyer {color:#64748b;font-size:.9rem;margin-bottom:12px}
    .offer-scenario {border-radius:20px;padding:5px 10px;font-size:.8rem;font-weight:600;display:inline-block}
    .risk-legend {display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
    </style>''', unsafe_allow_html=True)
    st.markdown('<span class="investor-badge">' + escape(t('FINANCING SIMULATION')) + '</span>', unsafe_allow_html=True)
    st.title(t('Choose your next financing opportunities') if page == 'Overview' else t('Compare your selection'))
    st.caption(t('Compare capital, payment horizons and scenarios before simulating an investment.'))
    st.caption(t('Rates are commercial or simulation assumptions, not calibrated credit-loss estimates or guaranteed returns.'))
    st.caption(t('Full invoices only. Gross gains assume full payment and are before costs; capital is at risk.'))
    st.markdown('<div class="risk-legend" aria-label="' + escape(t('Pricing scenario')) + '">' +
                ''.join(risk_badge(scenario, t) for scenario in SCENARIOS) + '</div>', unsafe_allow_html=True)
    st.caption(t('Colours describe the selected fictional scenario, not a verified credit rating.'))
    if page == 'Overview':
        st.button(t('View portfolio details'), key='investor_portfolio_details',
                  on_click=navigate, args=('Investor', 'Portfolio'))
        st.caption(t('1. Choose an invoice. 2. Review the financing. 3. Confirm the simulation.'))
    mode=st.radio(t('Quote calculation'),['Z-linked tariff (demo)','Expected-cashflow simulation'],format_func=t,key='investor_quote_mode',horizontal=True)
    if mode=='Z-linked tariff (demo)':
        st.info(t('Commercial demonstration tariff: 5%, 7%, 9% by accounting zone; 10% without accounts. Distress or invalid supplied accounts require manual review. No default probabilities are inferred.'))
    saved_filters = st.session_state.get('investor_filters', {})
    for key, default in dict(inv_budget=25000.0, inv_horizon=90, inv_scenario='All').items():
        st.session_state.setdefault(key, saved_filters.get(key, default))
    with st.container(border=True):
        a, b, c, d = st.columns([1.2, 1.1, 1, 1])
        budget = a.number_input(t('Total budget (€)'), min_value=1.0, max_value=1000000000.0, step=1000.0, key='inv_budget')
        horizon = b.selectbox(t('Maximum payment horizon'), [30, 60, 90, 180, 365, 36500],
            format_func=lambda days: t('{days} days', days=days), key='inv_horizon')
        scenario = c.selectbox(t('Scenario'), ['All'] + list(SCENARIOS) + ['Unknown'], format_func=t, key='inv_scenario')
        d.button(t('Reset filters'), on_click=reset_filters, use_container_width=True)
    st.session_state.investor_filters = dict(inv_budget=budget, inv_horizon=horizon, inv_scenario=scenario)
    if mode=='Z-linked tariff (demo)':
        entries=tariff_opportunities(invoices)
    else:
        unassessed = [i for i in invoices if assess_buyer(i)['value'] is None and not i.get('financing')]
        if unassessed:
            st.info(t('Return not calculated for {count} invoices: buyer accounting risk is not assessed.', count=len(unassessed)))
        use_scenario = illustrative_pricing_consent(t)
        if not use_scenario:
            st.info(t('No default yield: accounting ratios do not provide a calibrated probability of default. A documented pricing model or explicit simulation assumptions are required.'))
        entries = opportunities(invoices, st.session_state.get('investor_assignments'), st.session_state.get('investor_costs')) if use_scenario else []
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
                    risk_badge(entry['scenario'], t) +
                    '<div class="offer-amount">' + escape(euro(report['advance'])) + '</div>', unsafe_allow_html=True)
                st.caption(t('Buyer accounting risk') + ' · ' + t(assess_buyer(invoice)['band']))
                st.caption(t('Capital to advance'))
                st.write(t('Payment horizon') + ' · ' + t('{days} days', days=report['horizon_days']))
                st.write(t('Potential gross gain') + ' · **' + euro(report['gross_discount']) + '**')
                with st.expander(t('Returns and payment details')):
                    st.caption(t('Expected payment') + ' · ' + report['expected_payment_on'])
                    st.write(t('Full-payment proceeds') + ' · **' + euro(invoice['amount']) + '**')
                    st.write(t('Gross return over the operation') +
                             f" · **{holding_yield_percent(invoice['amount'], report['advance']):.2f} %**")
                    st.write(t('Gross annual yield (continuous)') + f" · **{report['annual_rate_percent']:.2f} %**")
                    st.caption(t('Returns assume full payment on the expected payment date, before costs and losses. They are not guaranteed.'))
                    if report['model_version']!='altman-tariff-demo-v1':
                        st.caption(t('Fixed transaction cost included in pricing: {cost}. The annual rate extrapolates the operation to one year; it is not the gain over this invoice period.', cost=euro(report['assumptions'].get('upfront_cost',0))))
                    else:
                        st.caption(t('The annual tariff is a commercial hypothesis. The period return uses the actual days to maturity; costs and losses are excluded.'))
                outstanding = buyer_outstanding_capital(invoices, invoice['buyer'])['outstanding_capital']
                if outstanding:
                    st.warning(t('Already exposed to this buyer') + ' · ' + euro(outstanding))
                st.caption(invoice['reference'])
                st.button(t('Review this financing'), key='dossier_' + identifier,
                    on_click=open_dossier, args=(entry, navigate), use_container_width=True, type='primary')
        with st.expander(t('Unavailable offers')):
            for entry in entries:
                if not entry['report']['acceptable']:
                    st.write(entry['invoice']['reference'])
                    for reason in entry['report']['blockers']:
                        st.caption(t(reason))
    hidden = sum(identifier not in {e['invoice']['id'] for e in visible} for identifier in selected)
    if hidden:
        st.info(t('{count} selected invoices are hidden by your filters.', count=hidden))
    if page == 'Overview' and not chosen:
        return
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
                st.caption(t('Selection terms: no SME recourse and no hypothetical insurance coverage.'))
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
