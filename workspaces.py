"""Presentation for each demo role; shared records and business rules stay unchanged."""
from engine import eligible


WORKSPACES = {
    'SME': {
        'pages': ['Overview', 'Upload an invoice', 'Invoice checks', 'Buyer accounts', 'Buyer confirmation', 'Portfolio'],
        'title': 'SME workspace',
        'headline': 'Turn your invoices into cash flow.',
        'description': 'Submit an invoice, complete its file and follow its financing.',
        'section': 'Your submitted invoices',
        'action': 'Upload an invoice',
        'target': 'Upload an invoice',
        'steps': ['Upload an invoice', 'Invoice review status', 'Invoice and transaction tracking'],
    },
    'Investor': {
        'pages': ['Overview', 'Compare opportunities', 'Portfolio', 'Simulation assumptions', 'Buyer accounts', 'Financing', 'Simulator'],
        'title': 'Investor workspace',
        'headline': 'Explore eligible invoices.',
        'description': 'Review eligibility, simulate an advance and track your portfolio.',
        'section': 'Invoices eligible for a financing simulation',
        'action': 'Explore financing',
        'target': 'Financing',
        'steps': ['Finance confirmed invoices', 'Explore financing scenarios', 'Invoice and transaction tracking'],
    },
    'Buyer': {
        'pages': ['Overview', 'Buyer confirmation', 'Buyer accounts', 'Portfolio'],
        'title': 'Buyer workspace',
        'headline': 'Review your invoices and share your annual accounts.',
        'description': 'Confirm or dispute supplier invoices and provide the financial statements used to assess your company.',
        'section': 'Invoices awaiting your decision',
        'action': 'Review buyer invoices',
        'target': 'Buyer confirmation',
        'steps': ['Review supplier invoices', 'Provide annual accounts', 'Track invoices payable'],
    },
}


def overview(role, invoices):
    """Return metrics (label, value, monetary) and the role's actionable invoices."""
    pending = [i for i in invoices if i['buyer_status'] == 'Pending' and not i.get('financing')]
    available = [i for i in invoices if eligible(i)]
    financed = [i for i in invoices if i.get('financing')]
    incomplete = [i for i in invoices if not i.get('financing') and
                  i['status'] != 'Closed' and (not i['identity'] or not i['documents'])]
    if role == 'SME':
        metrics = [('Submitted volume', sum(i['amount'] for i in invoices), True),
                   ('Invoice files awaiting review', len(incomplete), False),
                   ('Simulated advances', sum(i['financing'].get('sme_net_proceeds', i['financing']['advance']) for i in financed), True)]
        items = invoices
    elif role == 'Buyer':
        metrics = [('Invoices awaiting your decision', len(pending), False),
                   ('Amount awaiting buyer decision', sum(i['amount'] for i in pending), True),
                   ('Buyer accounts supplied', sum(bool(i.get('buyer_accounts')) for i in invoices), False)]
        items = pending
    else:
        metrics = [('Eligible for financing simulation', len(available), False),
                   ('Eligible invoice volume', sum(i['amount'] for i in available), True),
                   ('Outstanding simulated advances', sum(i['financing']['advance'] for i in financed
                                                          if i['status'] == 'Financed'), True)]
        items = available
    return metrics, items
