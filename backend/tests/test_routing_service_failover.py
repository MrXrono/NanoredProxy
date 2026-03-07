import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.models import Account, Proxy, ProxyAggregate, SystemSetting
from app.services.routing_service import select_proxy_for_account


@compiles(INET, 'sqlite')
def compile_inet_sqlite(_type, _compiler, **_kw):
    return 'TEXT'


@compiles(JSONB, 'sqlite')
def compile_jsonb_sqlite(_type, _compiler, **_kw):
    return 'TEXT'


@pytest.fixture()
def db_session():
    engine = create_engine('sqlite://', future=True, connect_args={'check_same_thread': False}, poolclass=StaticPool)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as db:
        db.add(SystemSetting(key='ab_strategy_split', value={'A': 100, 'B': 0}))
        db.add(SystemSetting(key='sticky_rating_threshold', value={'value': 50}))
        db.commit()
        yield db


def test_select_proxy_for_account_respects_exclude_proxy_ids(db_session):
    account = Account(id=1, username='us', password='us', account_type='country', country_code='us', is_enabled=True, is_dynamic=False)
    db_session.add(account)
    db_session.flush()

    proxy1 = Proxy(id=101, host='5.5.5.5', port=1080, status='online', is_enabled=True, is_quarantined=False, country_code='us')
    proxy2 = Proxy(id=102, host='6.6.6.6', port=1080, status='online', is_enabled=True, is_quarantined=False, country_code='us')
    db_session.add_all([proxy1, proxy2])
    db_session.flush()
    db_session.add_all([
        ProxyAggregate(proxy_id=proxy1.id, rating_score=220),
        ProxyAggregate(proxy_id=proxy2.id, rating_score=210),
    ])
    db_session.commit()

    selected = select_proxy_for_account(
        db_session,
        account,
        'A',
        exclude_proxy_ids={proxy1.id},
    )

    assert selected is not None
    assert selected.id == proxy2.id
