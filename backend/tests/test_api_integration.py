from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.db import Base, get_db
from app.main import app
from app.models import Account, AdminUser, SchedulerState, SystemSetting, TrafficRollup


@compiles(INET, 'sqlite')
def compile_inet_sqlite(_type, _compiler, **_kw):
    return 'TEXT'


@compiles(JSONB, 'sqlite')
def compile_jsonb_sqlite(_type, _compiler, **_kw):
    return 'TEXT'


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine('sqlite://', future=True, connect_args={'check_same_thread': False}, poolclass=StaticPool)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        db.add(AdminUser(id=1, username='admin', password='admin', is_active=True))
        db.add(Account(id=1, username='all', password='all', account_type='all', is_enabled=True, is_dynamic=False))
        db.add(SystemSetting(key='ab_strategy_split', value={'A': 50, 'B': 50}))
        db.add(SystemSetting(key='sticky_score_delta_threshold', value={'value': 0.15}))
        db.add(SchedulerState(worker_name='availability_checker', status='idle'))
        db.add(TrafficRollup(id=1, scope_type='global', scope_id='global', bucket_type='hour', bucket_start=datetime(2026, 3, 6, 10, 0, tzinfo=timezone.utc), bytes_in=1000, bytes_out=2000, sessions_count=2, connections_count=4))
        db.commit()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr('app.main.init_db', lambda: None)
    monkeypatch.setattr('app.services.runtime_state.redis_set_json', lambda *args, **kwargs: True)
    monkeypatch.setattr('app.services.runtime_state.redis_get_json', lambda *args, **kwargs: {})
    monkeypatch.setattr('app.services.runtime_state.redis_delete', lambda *args, **kwargs: True)
    monkeypatch.setattr('app.services.event_service.redis_publish_json', lambda *args, **kwargs: True)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _token(client):
    resp = client.post('/api/v1/admin/auth/login', json={'username': 'admin', 'password': 'admin'})
    assert resp.status_code == 200
    return resp.json()['access_token']


def test_import_proxy_and_list(client):
    token = _token(client)
    headers = {'Authorization': f'Bearer {token}'}
    resp = client.post('/api/v1/proxies/import/text', headers=headers, json={'text': '1.2.3.4:1080'})
    assert resp.status_code == 200
    assert resp.json()['inserted'] == 1
    resp = client.get('/api/v1/proxies', headers=headers)
    assert resp.status_code == 200
    assert resp.json()['total'] == 1


def test_proxy_actions_and_dashboard_charts(client):
    token = _token(client)
    headers = {'Authorization': f'Bearer {token}'}
    resp = client.post('/api/v1/proxies/import/text', headers=headers, json={'text': '1.2.3.4:1080'})
    proxy_id = client.get('/api/v1/proxies', headers=headers).json()['items'][0]['id']
    assert client.post(f'/api/v1/proxies/{proxy_id}/set-country', headers=headers, json={'country_code': 'de'}).status_code == 200
    assert client.post(f'/api/v1/proxies/{proxy_id}/quarantine', headers=headers).status_code == 200
    charts = client.get('/api/v1/dashboard/charts?period=24h', headers=headers)
    assert charts.status_code == 200
    data = charts.json()
    assert data['period'] == '24h'
    assert 'traffic_by_bucket' in data
    usage = client.get(f'/api/v1/proxies/{proxy_id}/routing-usage', headers=headers)
    assert usage.status_code == 200
    assert usage.json()['proxy_id'] == proxy_id


def test_worker_pause_and_resume(client):
    token = _token(client)
    headers = {'Authorization': f'Bearer {token}'}
    resp = client.post('/api/v1/system/workers/availability_checker/pause', headers=headers)
    assert resp.status_code == 200
    resp = client.get('/api/v1/system/workers', headers=headers)
    assert resp.json()['items'][0]['status'] == 'paused'
    resp = client.post('/api/v1/system/workers/availability_checker/resume', headers=headers)
    assert resp.status_code == 200
