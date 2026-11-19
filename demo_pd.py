"""Explicitly synthetic annual borrower-cohort aggregates for demonstration only."""
from datetime import date

from future_value import valuation_today

METHOD = 'fictional-annual-cohort-v1'
# Disjoint fictional groups: 200 buyers and four defaults in total.
# These are invented aggregate counts, not observations from invoiceflow.db.
COHORTS = {
    'All simulated buyers': (200, 4),
    'Simulated on-time buyers': (140, 1),
    'Simulated occasionally late buyers': (50, 2),
    'Simulated frequently late buyers': (10, 1),
}


def cohort_pd(buyers, defaults):
    if isinstance(buyers, bool) or isinstance(defaults, bool):
        raise ValueError('Cohort counts must be whole numbers with 0 <= defaults <= buyers.')
    if not isinstance(buyers, int) or not isinstance(defaults, int) or buyers < 0 or not 0 <= defaults <= buyers:
        raise ValueError('Cohort counts must be whole numbers with 0 <= defaults <= buyers.')
    return 100 * defaults / buyers if buyers else None


def demo_cohort(group='All simulated buyers', as_of=None):
    """Use the latest completed calendar year, never an unfinished annual window."""
    today = as_of or valuation_today()
    if group not in COHORTS:
        raise ValueError('Choose an available fictional borrower cohort.')
    buyers, defaults = COHORTS[group]
    year = today.year - 1
    return dict(method=METHOD, dataset_version=f'{METHOD}-{year}', group=group,
                observation_start=date(year, 1, 1).isoformat(),
                observation_end=date(year+1, 1, 1).isoformat(),
                borrowers=buyers, defaults=defaults, observed_pd_percent=cohort_pd(buyers, defaults),
                synthetic=True)


def verify_demo_cohort(metadata, annual_pd, origin, source_date, as_of):
    if not isinstance(metadata, dict) or metadata.get('method') != METHOD:
        raise ValueError('The fictional cohort report is invalid or inconsistent.')
    expected = demo_cohort(metadata.get('group'), as_of)
    if metadata != expected or annual_pd != expected['observed_pd_percent'] or origin != 'Illustrative assumptions' or source_date != expected['observation_end']:
        raise ValueError('The fictional cohort report is invalid or inconsistent.')
    return expected
