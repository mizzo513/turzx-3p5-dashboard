# SPDX-License-Identifier: GPL-3.0-or-later
"""Public GitHub Releases updater (read-only, no GitHub login/token required).

Only accept an update artifact published at the configured repository, verify
GitHub's SHA256 asset digest and the EXE hash in manifest.json. Checking never
changes the installed application. Actual installation requires user consent.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

from version_info import APP_VERSION
from update_manager import manifest_from_zip, version_tuple

REPOSITORY = 'mizzo513/turzx-3p5-dashboard'
LATEST_API = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
RELEASES_PAGE = f'https://github.com/{REPOSITORY}/releases'
MAX_DOWNLOAD_BYTES = 330 * 1024 * 1024
MAX_RELEASE_JSON_BYTES = 1024 * 1024
USER_AGENT = f'TURZX-Dashboard/{APP_VERSION} (Windows; public-release-updater)'


@dataclass(frozen=True)
class Release:
    version: str
    tag: str
    name: str
    notes: str
    url: str
    asset_url: str
    asset_size: int
    sha256: str


def _get_release_from_json(doc: dict) -> Release:
    """Validate all untrusted release metadata before allowing a download."""
    if not isinstance(doc, dict) or doc.get('draft') or doc.get('prerelease'):
        raise ValueError('正式版のリリースが見つかりません')
    tag = doc.get('tag_name')
    if not isinstance(tag, str) or not re.fullmatch(r'v\d+\.\d+\.\d+', tag):
        raise ValueError('GitHubのバージョン形式が不正です')
    version = tag[1:]
    asset_name = f'TURZX_Update_{tag}.zip'
    matches = [a for a in doc.get('assets', []) if isinstance(a, dict) and a.get('name') == asset_name]
    if len(matches) != 1:
        raise ValueError(f'更新ファイル {asset_name} がリリースにありません')
    asset = matches[0]
    expected_path = f'/{REPOSITORY}/releases/download/{tag}/{asset_name}'
    asset_url = asset.get('browser_download_url')
    if not isinstance(asset_url, str):
        raise ValueError('GitHubのダウンロードURLが不正です')
    parsed = urllib.parse.urlsplit(asset_url)
    if (parsed.scheme != 'https' or parsed.hostname != 'github.com'
            or parsed.username is not None or parsed.password is not None
            or parsed.port is not None or parsed.path != expected_path
            or parsed.query or parsed.fragment):
        raise ValueError('更新URLが指定GitHubリポジトリ以外を指しています')
    size = asset.get('size')
    if type(size) is not int or not 1024 <= size <= MAX_DOWNLOAD_BYTES:
        raise ValueError('更新ファイルのサイズが異常です')
    digest = asset.get('digest')
    if not isinstance(digest, str) or not re.fullmatch(r'sha256:[0-9a-fA-F]{64}', digest):
        raise ValueError('GitHubに更新ファイルのSHA256がありません。安全のため中止します')
    notes = doc.get('body') or ''
    return Release(version=version, tag=tag, name=str(doc.get('name') or tag)[:100],
                   notes=str(notes)[:1200], url=RELEASES_PAGE,
                   asset_url=asset_url, asset_size=size,
                   sha256=digest.removeprefix('sha256:').lower())


def fetch_latest_release(timeout: float = 8.0) -> Release:
    request = urllib.request.Request(
        LATEST_API,
        headers={'User-Agent': USER_AGENT, 'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2022-11-28'},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RELEASE_JSON_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RuntimeError('GitHub Releasesに公開された最新版がありません') from exc
        if exc.code == 403:
            raise RuntimeError('GitHub APIの利用回数制限またはアクセス制限が発生しました') from exc
        raise RuntimeError(f'GitHub APIへの接続に失敗しました (HTTP {exc.code})') from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f'GitHubに接続できません: {exc}') from exc
    if len(raw) > MAX_RELEASE_JSON_BYTES:
        raise ValueError('GitHubからの応答が大きすぎます')
    return _get_release_from_json(json.loads(raw.decode('utf-8')))


def is_newer(release: Release) -> bool:
    return version_tuple(release.version) > version_tuple(APP_VERSION)


def download_verified_update(release: Release, destination: Path, *, progress=None,
                             cancelled=None, timeout: float = 25.0) -> Path:
    """Download an official release ZIP and validate both GitHub and ZIP hashes."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(destination.name + '.part')
    sha = hashlib.sha256()
    downloaded = 0
    request = urllib.request.Request(
        release.asset_url,
        headers={'User-Agent': USER_AGENT, 'Accept': 'application/octet-stream'},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, staging.open('xb') as output:
            while True:
                if cancelled is not None and cancelled.is_set():
                    raise InterruptedError('ダウンロードをキャンセルしました')
                data = response.read(256 * 1024)
                if not data:
                    break
                downloaded += len(data)
                if downloaded > MAX_DOWNLOAD_BYTES or downloaded > release.asset_size:
                    raise ValueError('更新ファイルが宣言サイズを超えました')
                sha.update(data)
                output.write(data)
                if progress is not None:
                    progress(downloaded, release.asset_size)
        if downloaded != release.asset_size:
            raise ValueError('ファイルサイズが一致せず、ダウンロードが不完全です')
        if sha.hexdigest() != release.sha256:
            raise ValueError('GitHub公開のSHA256とダウンロード内容が一致しません')
        manifest = manifest_from_zip(staging)
        if manifest['version'] != release.version:
            raise ValueError('ReleaseのバージョンとZIP内のバージョンが一致しません')
        os.replace(staging, destination)
        return destination
    except Exception:
        staging.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise
