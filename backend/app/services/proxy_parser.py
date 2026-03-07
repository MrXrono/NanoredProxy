from typing import List, Dict


def parse_proxy_line(line: str) -> Dict | None:
    line = line.strip()
    if not line:
        return None
    if "@" in line:
        creds, addr = line.split("@", 1)
        user, password = creds.split(":", 1)
        host, port = addr.rsplit(":", 1)
        return {"host": host, "port": int(port), "auth_username": user, "auth_password": password, "has_auth": True}
    parts = line.split(":")
    if len(parts) == 2:
        host, port = parts
        return {"host": host, "port": int(port), "auth_username": None, "auth_password": None, "has_auth": False}
    if len(parts) == 4:
        host, port, user, password = parts
        return {"host": host, "port": int(port), "auth_username": user, "auth_password": password, "has_auth": True}
    raise ValueError(f"Unsupported proxy line format: {line}")


def parse_proxy_text(text: str) -> List[Dict]:
    items = []
    for raw in text.splitlines():
        parsed = parse_proxy_line(raw)
        if parsed:
            items.append(parsed)
    return items
