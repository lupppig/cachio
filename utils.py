from datetime import datetime
from email.utils import parsedate_to_datetime

from requests import Response

from error import DateDirectiveMissing


def to_date(date: str) -> datetime:
    dt = parsedate_to_datetime(date)
    return dt


def check_date(dd: Response) -> datetime:
    dt_str = dd.headers.get("Date")

    if not dt_str:
        raise DateDirectiveMissing("missind Date header")
    return to_date(dt_str)
