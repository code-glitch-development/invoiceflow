"""Calendar recency checks, not proof of the latest filing and never a fraud verdict."""
from calendar import monthrange
from datetime import date
from future_value import valuation_today


def _on(year,month,day):
    return date(year,month,min(day,monthrange(year,month)[1]))


def _months(value,count):
    offset=value.year*12+value.month-1+count
    return _on(offset//12,offset%12+1,value.day)


def latest_accounts_check(period_end,today=None):
    today=today or valuation_today()
    end=date.fromisoformat(period_end) if isinstance(period_end,str) else period_end
    if end>today:return dict(status='future',provided=end.isoformat(),message='The statement closing date is in the future.')
    latest=_on(today.year,end.month,end.day)
    if latest>today:latest=_on(today.year-1,end.month,end.day)
    grace_end=_months(latest,6)
    required=latest if today>grace_end else _on(latest.year-1,end.month,end.day)
    if end<required:status='obsolete'
    elif end<latest:status='previous_in_preparation_window'
    else:status='current'
    return dict(status=status,provided=end.isoformat(),latest_completed=latest.isoformat(),
                minimum_expected=required.isoformat(),preparation_window_ends=grace_end.isoformat(),
                basis='Closing month/day inferred from supplied accounts; six-month V1 preparation window; no external filing lookup')
