# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline tests for GitHub release metadata, SHA256 and downloaded ZIP."""
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import github_updater as gh
import update_manager


class FakeResponse:
    def __init__(self, data):
        self.buf=io.BytesIO(data)
    def __enter__(self):return self
    def __exit__(self,*args):return None
    def read(self,n=-1):return self.buf.read(n)


def fake_release(version='3.8.4',data=b'zipdata',url=None,digest=None):
    tag='v'+version
    filename=f'TURZX_Update_{tag}.zip'
    return dict(tag_name=tag,draft=False,prerelease=False,name='Release '+tag,
                body='Updates',assets=[dict(name=filename,size=len(data),
                browser_download_url=url or f'https://github.com/mizzo513/turzx-3p5-dashboard/releases/download/{tag}/{filename}',
                digest=digest if digest is not None else 'sha256:'+hashlib.sha256(data).hexdigest())])


def valid_zip(version='3.8.4'):
    exe=b'MZ'+bytes(range(256))*8
    meta=dict(app_id=update_manager.APP_ID,filename=update_manager.EXE_NAME,
              version=version,size=len(exe),sha256=hashlib.sha256(exe).hexdigest())
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w') as z:
        z.writestr('manifest.json',json.dumps(meta))
        z.writestr(update_manager.EXE_NAME,exe)
    return buf.getvalue()


class GitHubUpdaterTests(unittest.TestCase):
    def test_correct_release_and_newer(self):
        payload=valid_zip()
        release=gh._get_release_from_json(fake_release(data=payload))
        self.assertEqual(release.version,'3.8.4')
        self.assertTrue(gh.is_newer(release))

    def test_up_to_date(self):
        release=gh._get_release_from_json(fake_release('3.8.3',data=b'x'*2048))
        self.assertFalse(gh.is_newer(release))

    def test_reject_foreign_url(self):
        for url in ('http://github.com/mizzo513/turzx-3p5-dashboard/releases/download/v3.8.4/TURZX_Update_v3.8.4.zip',
                    'https://evil.invalid/update.zip',
                    'https://github.com/another/repo/releases/download/v3.8.4/TURZX_Update_v3.8.4.zip'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                gh._get_release_from_json(fake_release(data=b'x'*2048,url=url))

    def test_reject_bad_digest(self):
        with self.assertRaisesRegex(ValueError,'SHA256'):
            gh._get_release_from_json(fake_release(data=b'x'*2048,digest='sha256:unknown'))

    def test_valid_download(self):
        payload=valid_zip()
        release=gh._get_release_from_json(fake_release(data=payload))
        with tempfile.TemporaryDirectory() as tmp, patch.object(gh.urllib.request,'urlopen',return_value=FakeResponse(payload)):
            path=gh.download_verified_update(release,Path(tmp)/'update.zip')
            self.assertEqual(path.read_bytes(),payload)

    def test_reject_corrupt_download(self):
        payload=valid_zip()
        release=gh._get_release_from_json(fake_release(data=payload))
        corrupted=payload[:-1]+bytes([payload[-1]^1])
        with tempfile.TemporaryDirectory() as tmp, patch.object(gh.urllib.request,'urlopen',return_value=FakeResponse(corrupted)):
            with self.assertRaisesRegex(ValueError,'SHA256'):
                gh.download_verified_update(release,Path(tmp)/'update.zip')
            self.assertFalse((Path(tmp)/'update.zip').exists())

    def test_version_mismatch_in_zip(self):
        payload=valid_zip('3.8.5')
        release=gh._get_release_from_json(fake_release('3.8.4',data=payload))
        with tempfile.TemporaryDirectory() as tmp, patch.object(gh.urllib.request,'urlopen',return_value=FakeResponse(payload)):
            with self.assertRaisesRegex(ValueError,'バージョン'):
                gh.download_verified_update(release,Path(tmp)/'update.zip')

    def test_release_api_parsing(self):
        payload=valid_zip()
        response=json.dumps(fake_release(data=payload)).encode()
        with patch.object(gh.urllib.request,'urlopen',return_value=FakeResponse(response)):
            self.assertEqual(gh.fetch_latest_release().version,'3.8.4')


if __name__=='__main__':
    unittest.main()
