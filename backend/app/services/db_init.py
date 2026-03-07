from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import Base, engine
from app.models import Account, AdminUser, SchedulerState, SystemSetting

DEFAULT_SETTINGS = {
    'latency_threshold_ms': {'value': 1500},
    'speedtest_interval_hours': {'value': 6},
    'speedtest_pause_between_tests_minutes': {'value': 5},
    'speedtest_resume_after_idle_minutes': {'value': 10},
    'speedtest_parallelism': {'value': 1},
    'speed_min_mbps': {'download': 10, 'upload': 10},
    'quarantine_batch_size': {'value': 10},
    'quarantine_window_size': {'value': 5},
    'quarantine_pause_seconds': {'value': 2},
    'sticky_score_delta_threshold': {'value': 0.15},
    'ab_strategy_split': {'A': 50, 'B': 50},
}

DEFAULT_WORKERS = [
    'availability_checker', 'speedtest_runner', 'geo_resolver', 'aggregate_recalculator', 'account_reconciler'
]


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        for key, value in DEFAULT_SETTINGS.items():
            if not db.get(SystemSetting, key):
                db.add(SystemSetting(key=key, value=value))
        for worker in DEFAULT_WORKERS:
            if not db.get(SchedulerState, worker):
                db.add(SchedulerState(worker_name=worker, status='idle'))
        admin = db.scalar(select(AdminUser).where(AdminUser.username == settings.admin_username))
        if not admin:
            db.add(AdminUser(username=settings.admin_username, password=settings.admin_password, is_active=True))
        account = db.scalar(select(Account).where(Account.username == 'all'))
        if not account:
            db.add(Account(username='all', password='all', account_type='all', is_enabled=True, is_dynamic=False))
        db.commit()
