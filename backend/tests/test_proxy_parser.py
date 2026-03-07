from app.services.proxy_parser import parse_proxy_line, parse_proxy_text


def test_parse_proxy_line_formats():
    assert parse_proxy_line('1.2.3.4:1080') == {'host': '1.2.3.4', 'port': 1080, 'auth_username': None, 'auth_password': None, 'has_auth': False}
    assert parse_proxy_line('user:pass@5.6.7.8:1080') == {'host': '5.6.7.8', 'port': 1080, 'auth_username': 'user', 'auth_password': 'pass', 'has_auth': True}
    assert parse_proxy_line('9.9.9.9:1080:user:pass') == {'host': '9.9.9.9', 'port': 1080, 'auth_username': 'user', 'auth_password': 'pass', 'has_auth': True}


def test_parse_proxy_text_skips_empty_lines():
    items = parse_proxy_text('1.1.1.1:1080\n\n2.2.2.2:1080')
    assert len(items) == 2
