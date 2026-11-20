"""Flood request parameters (the four dates of the reference script + one explicit method switch)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ValidationError, model_validator

from ...core.config import Settings
from ...core.errors import InvalidRequestError
from ...schemas.common import Notice

# 'linear'     = DEFAULT. dB -> linear power, then post/pre, then log10 (the alternative the reference script keeps
#                commented out). A backscatter drop (water) gives a NEGATIVE value, which is what `lte(threshold)` selects.
# 'reference'  = the script's ACTIVE lines: post/pre of the raw dB values. The sign is inverted (flood -> positive),
#                so it selects the wrong side and flags land; kept only for comparison.
RatioDomain = Literal['reference', 'linear']


class FloodParams(BaseModel):
    """PRE and POST windows exactly as in the reference script (``filterDate``: end date is exclusive)."""

    pre_start: date
    pre_end: date
    post_start: date
    post_end: date
    ratio_domain: RatioDomain = 'linear'

    @model_validator(mode='after')
    def _order(self) -> 'FloodParams':
        if self.pre_end <= self.pre_start:
            raise ValueError('pre_end must be after pre_start')
        if self.post_end <= self.post_start:
            raise ValueError('post_end must be after post_start')
        if self.post_start < self.pre_end:
            raise ValueError('the POST window must not start before the PRE window ends')
        return self


def parse_params(raw: dict) -> FloodParams:
    try:
        return FloodParams(**raw)
    except ValidationError as exc:
        raise InvalidRequestError('The flood parameters are not valid: ' + '; '.join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())) from exc


def date_issues(p: FloodParams, settings: Settings, today: date | None = None) -> list[Notice]:
    """Application guards (not part of the reference method): future dates, Sentinel-1 era, window length."""
    today = today or datetime.now(timezone.utc).date()
    issues: list[Notice] = []
    if p.post_end > today + timedelta(days=1):
        issues.append(Notice(code='flood_future_date', message='The POST window ends in the future.'))
    earliest = date.fromisoformat(settings.flood_min_date)
    if p.pre_start < earliest:
        issues.append(Notice(code='flood_date_too_early',
                             message=f'Dates before {settings.flood_min_date} are not supported for flood detection.',
                             params={'min_date': settings.flood_min_date}))
    for name, a, b in (('pre', p.pre_start, p.pre_end), ('post', p.post_start, p.post_end)):
        days = (b - a).days
        if days > settings.flood_max_window_days:
            issues.append(Notice(code='window_too_long',
                                 message=f'The {name.upper()} window spans {days} days; the maximum is '
                                         f'{settings.flood_max_window_days}.',
                                 params={'window': name, 'days': days, 'max_days': settings.flood_max_window_days}))
    return issues
