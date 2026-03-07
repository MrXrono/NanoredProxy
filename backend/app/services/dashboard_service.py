from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Account, Proxy, Session as SessionModel, SessionConnection


def get_summary(db: Session) -> dict:
    return {
        'proxies_total': db.scalar(select(func.count()).select_from(Proxy)) or 0,
        'proxies_online': db.scalar(select(func.count()).select_from(Proxy).where(Proxy.status == 'online')) or 0,
        'proxies_degraded': db.scalar(select(func.count()).select_from(Proxy).where(Proxy.status == 'degraded')) or 0,
        'proxies_offline': db.scalar(select(func.count()).select_from(Proxy).where(Proxy.status == 'offline')) or 0,
        'proxies_quarantine': db.scalar(select(func.count()).select_from(Proxy).where(Proxy.is_quarantined.is_(True))) or 0,
        'country_unknown': db.scalar(select(func.count()).select_from(Proxy).where(Proxy.country_code.is_(None))) or 0,
        'accounts_total': db.scalar(select(func.count()).select_from(Account)) or 0,
        'accounts_enabled': db.scalar(select(func.count()).select_from(Account).where(Account.is_enabled.is_(True))) or 0,
        'active_sessions': db.scalar(select(func.count()).select_from(SessionModel).where(SessionModel.status == 'active')) or 0,
        'active_connections': db.scalar(select(func.count()).select_from(SessionConnection).where(SessionConnection.state == 'open')) or 0,
        'traffic_bytes_in': db.scalar(select(func.coalesce(func.sum(SessionModel.bytes_in), 0))) or 0,
        'traffic_bytes_out': db.scalar(select(func.coalesce(func.sum(SessionModel.bytes_out), 0))) or 0,
    }
