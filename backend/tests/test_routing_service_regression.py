import ipaddress

from app.services.routing_service import _normalize_client_ip


def test_normalize_client_ip_returns_ipaddress_for_valid_ipv4():
    normalized = _normalize_client_ip("127.0.0.1")
    assert normalized == ipaddress.ip_address("127.0.0.1")


def test_normalize_client_ip_keeps_invalid_values_unchanged():
    assert _normalize_client_ip("not-an-ip") == "not-an-ip"
