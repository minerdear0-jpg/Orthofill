import asyncio
import base64
import re

from aiohttp.test_utils import TestClient, TestServer

from receiver.app import PAGE, ServerConfig, make_app


def test_page_no_external_urls():
    html = PAGE.read_text(encoding='utf-8')
    assert '<title>' in html
    assert not re.search(r'(?:src|href)\s*=\s*["\']?(?:https?:)?//', html)
    assert not re.search(r'https?://', html)
    assert '.innerHTML' not in html        # текст событий — только textContent


def test_page_requires_password(tmp_path):
    cfg = ServerConfig(db=tmp_path / 'rx.db', keys={'k'}, admin_password='p')

    async def go():
        async with TestClient(TestServer(make_app(cfg))) as c:
            assert (await c.get('/')).status == 401
            auth = {'Authorization': 'Basic ' + base64.b64encode(b'a:p').decode()}
            r = await c.get('/', headers=auth)
            assert r.status == 200 and 'Orthofill' in await r.text()
            assert "default-src 'none'" in r.headers['Content-Security-Policy']
    asyncio.run(go())
