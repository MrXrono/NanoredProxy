from app.services import runtime_state


class DummyStore(dict):
    def get(self, key):
        return super().get(key)

    def set(self, key, value, ex=None):
        self[key] = value

    def delete(self, key):
        self.pop(key, None)


def test_kill_request_roundtrip(monkeypatch):
    store = DummyStore()

    monkeypatch.setattr(runtime_state, 'redis_set_json', lambda key, value, ex=None: store.set(key, value) or True)
    monkeypatch.setattr(runtime_state, 'redis_get_json', lambda key, default=None: store.get(key) if key in store else default)
    monkeypatch.setattr(runtime_state, 'redis_delete', lambda key: store.delete(key) or True)

    runtime_state.request_kill('abc', 'test')
    assert runtime_state.is_kill_requested('abc') is True
    assert runtime_state.get_kill_reason('abc') == 'test'
    runtime_state.clear_kill('abc')
    assert runtime_state.is_kill_requested('abc') is False
