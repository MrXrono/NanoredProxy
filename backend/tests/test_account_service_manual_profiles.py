from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.models import Account, Proxy
from app.services.account_service import reconcile_accounts


def make_db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def test_reconcile_keeps_manual_country_profiles_enabled():
    db = make_db()
    db.add(Account(id=1, username="uz", password="all", account_type="country", country_code="uz", is_enabled=True, is_dynamic=False))
    db.commit()

    touched = reconcile_accounts(db)
    account = db.scalar(select(Account).where(Account.username == "uz"))

    assert touched == 0
    assert account is not None
    assert account.is_enabled is True
    assert account.is_dynamic is False


def test_reconcile_reenables_existing_dynamic_country_profile():
    db = make_db()
    db.add(Account(id=1, username="uz", password="uz", account_type="country", country_code="uz", is_enabled=False, is_dynamic=True))
    db.add_all([
        Proxy(id=1, host="10.0.0.1", port=1080, status="online", country_code="uz", is_enabled=True, is_quarantined=False),
        Proxy(id=2, host="10.0.0.2", port=1080, status="online", country_code="uz", is_enabled=True, is_quarantined=False),
    ])
    db.commit()

    reconcile_accounts(db)
    account = db.scalar(select(Account).where(Account.username == "uz"))

    assert account is not None
    assert account.password == "uz"
    assert account.is_dynamic is True
    assert account.is_enabled is True
