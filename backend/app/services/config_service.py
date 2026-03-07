from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account


def build_proxychains_bundle(db: Session, listen_host: str = '127.0.0.1', listen_port: int = 1080) -> str:
    accounts = list(db.scalars(select(Account).where(Account.is_enabled.is_(True)).order_by(Account.username.asc())))
    lines = ['# NanoredProxy unified proxychains profiles', '# Copy the block you need into proxychains.conf', '']
    for account in accounts:
        label = account.country_code or 'all'
        lines.extend([
            f'[profile:{label}]',
            '[ProxyList]',
            f'socks5 {listen_host} {listen_port} {account.username} {account.password}',
            '',
        ])
    return '\n'.join(lines).strip() + '\n'
