from datetime import datetime, timedelta
from typing import Tuple

import pytz


def date_start_end(
    start_delta: timedelta = timedelta(hours=1),
    duration_delta: timedelta = timedelta(hours=1),
    timezone="US/Eastern",
    force_same_day=True,
) -> Tuple[datetime, datetime]:
    tz = pytz.timezone(timezone)
    now = datetime.utcnow()
    start_dtz = tz.fromutc(now) + start_delta
    end_dtz = start_dtz + duration_delta
    if end_dtz.time() < start_dtz.time() and force_same_day:
        start_dtz = end_dtz
        end_dtz = start_dtz + duration_delta
    return (
        start_dtz,
        end_dtz,
    )
