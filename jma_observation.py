# -*- coding: utf-8 -*-
"""Best-effort JMA precipitation *observations*, stdlib only.

The JMA map's JSON/tile routes are undocumented website internals, not a public
stable API. Never infer 'no rain' from missing/transparent/out-of-coverage data.
For one selected point, only download the latest HRPN tile(s) and an AMeDAS map.
No location history, credentials, or large images are stored on disk.
Source attribution: Japan Meteorological Agency (https://www.jma.go.jp/).
"""
from __future__ import annotations

import datetime as dt
import json
import math
import struct
import urllib.error
import urllib.request
import zlib

UTC = dt.timezone.utc
RADAR_INDEX = 'https://www.jma.go.jp/bosai/jmatile/data/nowc/targetTimes_N1.json'
AMEDAS_LATEST = 'https://www.jma.go.jp/bosai/amedas/data/latest_time.txt'
AMEDAS_TABLE = 'https://www.jma.go.jp/bosai/amedas/const/amedastable.json'
JMA_BASE = 'https://www.jma.go.jp/bosai'
RADAR_ZOOM = 8
MAX_RADAR_AGE_MIN = 30
MAX_AMEDAS_AGE_MIN = 35
MAX_STATION_KM = 15
USER_AGENT = 'TURZXDashboard/3.9.9 (personal weather display)'
# JMA rain legend RGB; 1..8 represent 0-1,1-5,5-10,10-20,20-30,30-50,50-80,80+ mm/h.
JMA_RAIN_RGB = ((242, 242, 255), (160, 210, 255), (33, 140, 255),
                (0, 65, 255), (250, 245, 0), (255, 153, 0),
                (255, 40, 0), (180, 0, 104))
_station_table_cache = None


def _bytes(url, max_bytes=1024 * 1024):
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': '*/*'})
    with urllib.request.urlopen(req, timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f'JMA HTTP {response.status}')
        data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError('JMA response exceeds size limit')
        return data


def _json(url, max_bytes=1024 * 1024):
    return json.loads(_bytes(url, max_bytes).decode('utf-8-sig'))


def _utcnow(now=None):
    now = now or dt.datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError('time must be timezone-aware')
    return now.astimezone(UTC)


def _fresh(instant, now, max_age_min):
    if instant.tzinfo is None:
        return False
    age = (_utcnow(now) - instant.astimezone(UTC)).total_seconds()
    return -300 <= age <= max_age_min * 60


def _utc_stamp(stamp):
    return dt.datetime.strptime(stamp, '%Y%m%d%H%M%S').replace(tzinfo=UTC)


def latest_radar_frame(frames, now=None):
    """Select most recent *analysis* frame, reject future/old/stale frames."""
    candidates = []
    if not isinstance(frames, list):
        return None
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        base, valid = frame.get('basetime'), frame.get('validtime')
        if not (isinstance(base, str) and isinstance(valid, str) and base == valid):
            continue
        if 'hrpns' not in frame.get('elements', []):
            continue
        try:
            when = _utc_stamp(valid)
        except (ValueError, TypeError):
            continue
        if _fresh(when, now, MAX_RADAR_AGE_MIN):
            candidates.append((when, frame))
    return max(candidates, key=lambda pair: pair[0])[1] if candidates else None


def tile_position(lat, lon, zoom=RADAR_ZOOM):
    """Web Mercator pixel coordinates at the center of the map point."""
    lat = max(-85.0511, min(85.0511, float(lat)))
    lon = float(lon)
    n = 2 ** int(zoom)
    x = (lon + 180) / 360 * n * 256
    rad = math.radians(lat)
    y = (1 - math.asinh(math.tan(rad)) / math.pi) / 2 * n * 256
    return math.floor(x), math.floor(y)


def radar_url(frame, x, y, zoom=RADAR_ZOOM):
    base, valid = frame['basetime'], frame['validtime']
    if len(base) != 14 or len(valid) != 14 or not base.isdigit() or not valid.isdigit():
        raise ValueError('Invalid JMA radar timestamp')
    return f'{JMA_BASE}/jmatile/data/nowc/{base}/none/{valid}/surf/hrpns/{zoom}/{x}/{y}.png'


def _unfilter_rows(raw, width, height, bytes_per_pixel):
    stride = width * bytes_per_pixel
    if len(raw) != (stride + 1) * height:
        raise ValueError('Unexpected PNG image data length')
    output = bytearray(width * height * bytes_per_pixel)
    last = bytearray(stride)
    for y in range(height):
        offset = y * (stride + 1)
        filter_type = raw[offset]
        scan = bytearray(raw[offset + 1:offset + stride + 1])
        for pos in range(stride):
            a = scan[pos - bytes_per_pixel] if pos >= bytes_per_pixel else 0
            b = last[pos]
            c = last[pos - bytes_per_pixel] if pos >= bytes_per_pixel else 0
            if filter_type == 1:
                scan[pos] = (scan[pos] + a) & 255
            elif filter_type == 2:
                scan[pos] = (scan[pos] + b) & 255
            elif filter_type == 3:
                scan[pos] = (scan[pos] + (a + b) // 2) & 255
            elif filter_type == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                predictor = a if pa <= pb and pa <= pc else b if pb <= pc else c
                scan[pos] = (scan[pos] + predictor) & 255
            elif filter_type != 0:
                raise ValueError('Unsupported PNG filter')
        output[y * stride:(y + 1) * stride] = scan
        last = scan
    return output


def decode_png_rgba(png):
    """CRC-validated 256x256 PNG decoder (8-bit RGBA/RGB/palette/grey)."""
    if not png.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Not a PNG')
    pos, chunks, palette, transparency = 8, [], None, None
    width = height = typ = None
    seen_iend = False
    while pos + 12 <= len(png):
        size = struct.unpack_from('>I', png, pos)[0]
        kind = png[pos + 4:pos + 8]
        end = pos + 12 + size
        if size > 1024 * 1024 or end > len(png):
            raise ValueError('Oversized or truncated PNG chunk')
        data = png[pos + 8:pos + 8 + size]
        crc_read = struct.unpack_from('>I', png, pos + 8 + size)[0]
        if zlib.crc32(kind + data) & 0xffffffff != crc_read:
            raise ValueError('Corrupt PNG CRC')
        pos = end
        if kind == b'IHDR':
            width, height, depth, typ, compression, filtering, interlace = struct.unpack('>IIBBBBB', data)
            if (width, height) != (256, 256) or depth != 8 or typ not in (0, 2, 3, 4, 6) or (compression, filtering, interlace) != (0, 0, 0):
                raise ValueError('Unsupported JMA tile image')
        elif kind == b'PLTE':
            palette = data
        elif kind == b'tRNS':
            transparency = data
        elif kind == b'IDAT':
            chunks.append(data)
        elif kind == b'IEND':
            if size != 0:
                raise ValueError('Invalid PNG IEND')
            seen_iend = True
            break
    if width is None or not chunks or not seen_iend:
        raise ValueError('PNG tile data is missing')
    bpp = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[typ]
    expected = (width * bpp + 1) * height
    inflater = zlib.decompressobj()
    raw = inflater.decompress(b''.join(chunks), expected + 1)
    if len(raw) > expected or inflater.unconsumed_tail:
        raise ValueError('PNG uncompressed size is too large')
    raw += inflater.flush()
    if len(raw) != expected or not inflater.eof:
        raise ValueError('Invalid PNG data stream')
    rows = _unfilter_rows(raw, width, height, bpp)
    if typ == 6:
        return rows
    out = bytearray(width * height * 4)
    for pixel in range(width * height):
        idx = pixel * bpp
        if typ == 2:
            rgba = (*rows[idx:idx + 3], 255)
        elif typ == 0:
            g = rows[idx]
            rgba = (g, g, g, 255)
        elif typ == 4:
            g, a = rows[idx:idx + 2]
            rgba = (g, g, g, a)
        else:
            n = rows[idx]
            if palette is None or 3 * n + 2 >= len(palette):
                raise ValueError('Missing palette entry')
            rgba = (palette[3 * n], palette[3 * n + 1], palette[3 * n + 2],
                    transparency[n] if transparency and n < len(transparency) else 255)
        out[4 * pixel:4 * pixel + 4] = bytes(rgba)
    return out


def rain_class(red, green, blue, alpha):
    """Return 0 for transparent, 1-8 for a precipitation intensity, None if unknown."""
    if alpha < 128:
        return 0
    for index, (r, g, b) in enumerate(JMA_RAIN_RGB, 1):
        if abs(red - r) <= 6 and abs(green - g) <= 6 and abs(blue - b) <= 6:
            return index
    return None


def sample_radar_tiles(frame, lat, lon, fetch_tile=None, zoom=RADAR_ZOOM, radius=2):
    """Return positive rain class or 0/None. Never trust no-data as 'dry'."""
    fetch_tile = fetch_tile or _bytes
    x, y = tile_position(lat, lon, zoom)
    caches = {}
    observed = []
    unavailable = False
    for px in range(x - radius, x + radius + 1):
        for py in range(y - radius, y + radius + 1):
            tile_key = (px // 256, py // 256)
            if tile_key not in caches:
                url = radar_url(frame, *tile_key, zoom)
                try:
                    caches[tile_key] = decode_png_rgba(fetch_tile(url))
                except (OSError, RuntimeError, ValueError, urllib.error.URLError):
                    caches[tile_key] = None
            image = caches[tile_key]
            if image is None:
                unavailable = True
                continue
            offset = ((py % 256) * 256 + px % 256) * 4
            k = rain_class(*image[offset: offset + 4])
            if k is None:
                unavailable = True
            else:
                observed.append(k)
    if not observed:
        return None
    highest = max(observed)
    # Unknown pixels may hide precipitation; only declare a positive observation.
    return highest if highest > 0 else None if unavailable else 0


def fetch_radar(city, now=None):
    now = _utcnow(now)
    frames = _json(RADAR_INDEX, 64 * 1024)
    frame = latest_radar_frame(frames, now)
    if frame is None:
        raise ValueError('JMA radar timestamp missing or older than 30 minutes')
    level = sample_radar_tiles(frame, city['latitude'], city['longitude'])
    return {'level': level, 'observed_at': _utc_stamp(frame['validtime']).isoformat(),
            'provider': '気象庁 降水ナウキャスト', 'status': 'rain' if level and level > 0 else 'unconfirmed'}


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dp, dl = p2 - p1, math.radians(float(lon2) - float(lon1))
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0, 1 - a)))


def station_candidates(table, city, limit_km=MAX_STATION_KM):
    values = []
    if not isinstance(table, dict):
        return values
    for code, station in table.items():
        try:
            lat = station['lat'][0] + station['lat'][1] / 60
            lon = station['lon'][0] + station['lon'][1] / 60
            distance = haversine_km(city['latitude'], city['longitude'], lat, lon)
            if distance <= limit_km:
                values.append((distance, str(code), station.get('kjName', str(code))))
        except (ValueError, KeyError, IndexError, TypeError, ZeroDivisionError):
            continue
    return sorted(values)


def _good_amedas_number(raw):
    if not isinstance(raw, (tuple, list)) or len(raw) < 2:
        return None
    try:
        value, quality = float(raw[0]), int(raw[1])
        return value if quality in (0, 8) and math.isfinite(value) else None
    except (ValueError, TypeError, OverflowError):
        return None


def pick_nearby_amedas(table, current_map, city, limit_km=MAX_STATION_KM):
    for distance, code, name in station_candidates(table, city, limit_km):
        record = current_map.get(code) if isinstance(current_map, dict) else None
        if not isinstance(record, dict):
            continue
        precip = _good_amedas_number(record.get('precipitation10m'))
        sunshine = _good_amedas_number(record.get('sun10m'))
        if precip is not None or sunshine is not None:
            return {'station': name, 'distance_km': round(distance, 1),
                    'precipitation10m': precip, 'sun10m': sunshine}
    return None


def fetch_amedas(city, now=None):
    global _station_table_cache
    now = _utcnow(now)
    latest = _bytes(AMEDAS_LATEST, 256).decode('ascii').strip()
    stamp = dt.datetime.fromisoformat(latest)
    if not _fresh(stamp, now, MAX_AMEDAS_AGE_MIN):
        raise ValueError('AMeDAS observation timestamp is stale')
    when = stamp.astimezone(dt.timezone(dt.timedelta(hours=9)))
    name = when.strftime('%Y%m%d%H%M00')
    map_data = _json(f'{JMA_BASE}/amedas/data/map/{name}.json')
    if _station_table_cache is None:
        _station_table_cache = _json(AMEDAS_TABLE)
    picked = pick_nearby_amedas(_station_table_cache, map_data, city)
    if picked is None:
        return None
    picked['observed_at'] = stamp.astimezone(UTC).isoformat()
    picked['provider'] = '気象庁 アメダス'
    return picked


def fetch_observations(city, now=None):
    """Fetch independently; one unavailable JMA endpoint must not mask the other."""
    result = {'radar': None, 'amedas': None, 'errors': []}
    # The source is a public website, and may change without notice.
    for name, fetch in (('radar', fetch_radar), ('amedas', fetch_amedas)):
        try:
            result[name] = fetch(city, now=now)
        except Exception as exc:
            result['errors'].append(f'{name}: {type(exc).__name__}: {str(exc)[:160]}')
    return result
