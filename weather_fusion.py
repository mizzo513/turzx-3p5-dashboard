# SPDX-License-Identifier: GPL-3.0-or-later
"""Comprehensive current-weather observation for TURZX.

Adapted from the user's WeatherTransitWidget: observed JMA rain > nearby
AMeDAS > Open-Meteo model. Only the current weather icon/label changes;
the selected provider continues to supply temperature and daily forecasts.
JMA website tile endpoints are best-effort undocumented interfaces.
"""
from __future__ import annotations
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from jma_observation import fetch_observations
from weather_judgement import decide_current_weather

ENDPOINT = 'https://api.open-meteo.com/v1/forecast'
CURRENT_FIELDS = 'weather_code,is_day,cloud_cover,precipitation,rain,showers,snowfall'


def fetch_model_current(conf, opener=urlopen):
    params = {
        'latitude': float(conf['weather_latitude']),
        'longitude': float(conf['weather_longitude']),
        'current': CURRENT_FIELDS,
        'timezone': 'Asia/Tokyo',
        'forecast_days': 1,
    }
    request = Request(
        ENDPOINT + '?' + urlencode(params),
        headers={'User-Agent': 'TURZXDashboard/3.9.9 (personal use)',
                 'Accept': 'application/json'},
    )
    with opener(request, timeout=12) as reply:
        raw = reply.read(131073)
    if len(raw) > 131072:
        raise ValueError('Open-Meteo current response too large')
    doc = json.loads(raw.decode('utf-8'))
    if not isinstance(doc, dict) or not isinstance(doc.get('current'), dict):
        raise ValueError('Open-Meteo current conditions missing')
    current = doc['current']
    if current.get('weather_code') is None:
        raise ValueError('Open-Meteo current weather code missing')
    return current


def fetch_weather_evidence(conf):
    """Fetch observations independently, returning a safe partial result.

    An unavailable radar/AMeDAS endpoint is never interpreted as no rain.
    Request this on a worker thread, never the clock/USB drawing loop.
    """
    evidence = {'model': None, 'observations': {}, 'errors': []}
    try:
        evidence['model'] = fetch_model_current(conf)
    except Exception as exc:
        evidence['errors'].append('Open-Meteo: ' + type(exc).__name__ + ': ' + str(exc)[:140])
    try:
        city = {'latitude': float(conf['weather_latitude']),
                'longitude': float(conf['weather_longitude'])}
        observations = fetch_observations(city)
        evidence['observations'] = observations
        evidence['errors'].extend(observations.get('errors') or [])
    except Exception as exc:
        evidence['errors'].append('JMA: ' + type(exc).__name__ + ': ' + str(exc)[:140])
    return evidence


def judge_weather(baseline, evidence, now=None):
    """Return fused CurrentWeather, or None if only unavailable evidence exists.

    With no Open-Meteo data, positive JMA rain/snow observations may still
    override the chosen weather provider, but a dry/unknown radar result must
    not replace the chosen provider's existing condition.
    """
    if not isinstance(evidence, dict):
        return None
    model = evidence.get('model')
    observations = evidence.get('observations') or {}
    if isinstance(model, dict):
        return decide_current_weather({'current': model}, observations, now=now)
    if baseline is None:
        return None
    baseline_code = getattr(baseline, 'code', None)
    fallback = {
        'weather_code': baseline_code if baseline_code is not None else 3,
        'precipitation': getattr(baseline, 'precip_mm', None),
    }
    selected = decide_current_weather({'current': fallback}, observations, now=now)
    if selected.source.startswith('気象庁'):
        return selected
    return None
