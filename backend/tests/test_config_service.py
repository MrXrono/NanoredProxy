from types import SimpleNamespace

from app.services.config_service import build_proxychains_bundle


class FakeScalarResult:
    def __init__(self, items):
        self._items = items

    def __iter__(self):
        return iter(self._items)


class FakeDB:
    def __init__(self, items):
        self.items = items

    def scalars(self, _stmt):
        return FakeScalarResult(self.items)


def test_build_proxychains_bundle_contains_all_profiles():
    db = FakeDB([
        SimpleNamespace(username='all', password='all', country_code=None, is_enabled=True),
        SimpleNamespace(username='de', password='de', country_code='de', is_enabled=True),
    ])
    content = build_proxychains_bundle(db, listen_host='127.0.0.1', listen_port=1080)
    assert '[profile:all]' in content
    assert '[profile:de]' in content
    assert 'socks5 127.0.0.1 1080 de de' in content
