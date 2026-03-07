from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Account, Proxy, Session as ProxySession


def list_accounts(db: Session) -> list[dict]:
    accounts = list(db.scalars(select(Account).order_by(Account.username.asc())))
    out = []
    for account in accounts:
        active_sessions = db.scalar(select(func.count()).select_from(ProxySession).where(ProxySession.account_id == account.id, ProxySession.status == 'active')) or 0
        if account.account_type == 'all':
            working = db.scalar(select(func.count()).select_from(Proxy).where(Proxy.status.in_(['online','degraded']), Proxy.is_enabled.is_(True), Proxy.is_quarantined.is_(False))) or 0
        else:
            working = db.scalar(select(func.count()).select_from(Proxy).where(Proxy.country_code == account.country_code, Proxy.status.in_(['online','degraded']), Proxy.is_enabled.is_(True), Proxy.is_quarantined.is_(False))) or 0
        out.append({'id': account.id, 'username': account.username, 'password': account.password, 'account_type': account.account_type, 'country_code': account.country_code, 'is_enabled': account.is_enabled, 'active_sessions': active_sessions, 'working_proxies': working})
    return out


def reconcile_accounts(db: Session) -> int:
    countries = db.execute(
        select(Proxy.country_code, func.count(Proxy.id))
        .where(Proxy.status == 'online', Proxy.is_enabled.is_(True), Proxy.is_quarantined.is_(False), Proxy.country_code.is_not(None))
        .group_by(Proxy.country_code)
    ).all()
    country_counts = {cc.lower(): count for cc, count in countries if cc}
    touched = 0
    dynamic_accounts = {
        a.username: a
        for a in db.scalars(select(Account).where(Account.account_type == 'country', Account.is_dynamic.is_(True)))
    }
    for cc, count in country_counts.items():
        if count >= 2:
            if cc in dynamic_accounts:
                dynamic_accounts[cc].is_enabled = True
                dynamic_accounts[cc].last_reconciled_at = datetime.utcnow()
            else:
                db.add(Account(username=cc, password=cc, account_type='country', country_code=cc, is_enabled=True, is_dynamic=True, last_reconciled_at=datetime.utcnow()))
            touched += 1
    for username, account in dynamic_accounts.items():
        if country_counts.get(username, 0) < 2:
            account.is_enabled = False
            account.last_reconciled_at = datetime.utcnow()
            touched += 1
    db.commit()
    return touched
