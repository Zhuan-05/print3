import json
import os
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

import auto_setup
from scripts.run_local import export_google_settings


def prefill(query):
    return 'https://docs.google.com/forms/d/e/PUBLIC/viewform?' + urlencode(query)


def test_form_parse_maps_markers_without_field_order():
    result = auto_setup.parse_form('https://docs.google.com/forms/d/EDITOR/edit?usp=sharing',
        prefill({'entry.22': 'PRINT3D_BINDING_TOKEN', 'entry.11': '123456789', 'entry.33': 'PLA'}))
    assert result == {'GOOGLE_FORM_ID': 'EDITOR',
        'GOOGLE_FORM_URL': 'https://docs.google.com/forms/d/e/PUBLIC/viewform',
        'FORM_TELEGRAM_ENTRY': 'entry.11', 'FORM_BINDING_ENTRY': 'entry.22'}


@pytest.mark.parametrize('editor,public', [
    ('https://docs.google.com.evil/forms/d/EDITOR/edit', prefill({'entry.1': '123456789', 'entry.2': 'PRINT3D_BINDING_TOKEN'})),
    ('https://docs.google.com/forms/d/EDITOR/edit', 'https://evil.com/forms/d/e/PUBLIC/viewform'),
    ('https://docs.google.com/forms/d/EDITOR/edit', prefill({'entry.1': '123456789'})),
    ('https://docs.google.com/forms/d/EDITOR/edit', prefill({'entry.1': '123456789', 'entry.2': '123456789', 'entry.3': 'PRINT3D_BINDING_TOKEN'})),
])
def test_form_parse_rejects_invalid_inputs(editor, public):
    with pytest.raises(ValueError):
        auto_setup.parse_form(editor, public)


def message(text='/setup@MyBot ABC', uid=42, chat=-100, kind='supergroup', sender=None):
    return SimpleNamespace(message=SimpleNamespace(text=text, chat_id=chat,
        chat=SimpleNamespace(type=kind), from_user=SimpleNamespace(id=uid, is_bot=False), sender_chat=sender))


def test_pairing_rejects_wrong_code_target_and_anonymous_sender():
    assert auto_setup.pairing_message(message(), 'ABC', 'MyBot') == ('group', -100, 42)
    assert auto_setup.pairing_message(message('/setup@OtherBot ABC'), 'ABC', 'MyBot') is None
    assert auto_setup.pairing_message(message('/setup WRONG'), 'ABC', 'MyBot') is None
    assert auto_setup.pairing_message(message(sender=object()), 'ABC', 'MyBot') is None
    assert auto_setup.pairing_message(message('/setup ABC', chat=42, kind='private'), 'ABC', 'MyBot') == ('owner', 42)


def test_google_export_contains_only_properties_and_escapes(tmp_path):
    settings = SimpleNamespace(webhook_secret='a' * 64)
    target = export_google_settings(tmp_path, 'https://test.trycloudflare.com/webhooks/google-form', settings)
    text = target.read_text()
    payload = text.split('setProperties(', 1)[1].split(', false)', 1)[0]
    assert json.loads(payload) == {'WEBHOOK_SECRET': 'a' * 64,
        'WEBHOOK_URL': 'https://test.trycloudflare.com/webhooks/google-form'}
    assert os.stat(target).st_mode & 0o777 == 0o600
    assert 'BOT_TOKEN' not in text


def test_ready_rejects_placeholder_and_never_changes_env(tmp_path, monkeypatch):
    monkeypatch.setattr(auto_setup, 'ROOT', tmp_path)
    target = tmp_path / '.env'
    target.write_text('BOT_TOKEN=REPLACE_WITH_TOKEN\n')
    original = target.read_bytes()
    assert not auto_setup.ready()
    assert target.read_bytes() == original


def test_pairing_requires_group_sender_to_match_paired_owner(monkeypatch):
    import asyncio
    calls = []
    class FakeBot:
        username = 'MyBot'
        id = 1
        def __init__(self, token): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get_webhook_info(self): return SimpleNamespace(url='')
        async def get_chat_member(self, chat, uid):
            calls.append(chat)
            return SimpleNamespace(status='member')
        async def get_updates(self, **kwargs):
            updates = [message('/setup ABC', uid=42, chat=42, kind='private'),
                       message('/setup@MyBot ABC', uid=43, chat=-101),
                       message('/setup@MyBot ABC', uid=42, chat=-102)]
            for n, update in enumerate(updates): update.update_id = n
            return updates
    monkeypatch.setattr(auto_setup, 'Bot', FakeBot)
    monkeypatch.setattr(auto_setup.secrets, 'token_hex', lambda n: 'ABC')
    assert asyncio.run(auto_setup.pair('test', True)) == ('-102', '42')
    assert calls == [-102]


def test_share_archive_excludes_private_runtime_files(tmp_path, monkeypatch):
    from scripts import build_release
    from zipfile import ZipFile
    root = tmp_path / 'source'
    root.mkdir()
    (root / 'README.md').write_text('public')
    (root / '.env').write_text('BOT_TOKEN=SECRET')
    (root / 'orders.sqlite3').write_text('private')
    (root / 'ConfigurePrint3D.gs').write_text('private secret')
    monkeypatch.setattr(build_release, 'ROOT', root)
    monkeypatch.setattr(build_release, 'FILES', ['README.md'])
    target = build_release.build()
    with ZipFile(target) as archive:
        assert archive.namelist() == ['print3d/README.md']
        assert archive.read('print3d/README.md') == b'public'
