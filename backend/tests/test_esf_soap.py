"""ЭСФ SOAP-транспорт: офлайн-проверка сборки/подписи authSign-тикета.

Живые вызовы к test3.esf.kgd.gov.kz здесь НЕ гоняются (внешний гос-стенд, нет в CI).
Проверяем детерминированное: структуру тикета и что enveloped-XMLDSIG самоверифицируется.
Серт генерируем на лету (валидный), боевой/тестовый p12 в репо не коммитим.
"""

import datetime
import tempfile

import pytest
from lxml import etree

from app.esf import soap


def _make_p12(path: str, pin: str):
    """RSA-серт валидный на сейчас → PKCS12, чтобы проверить путь подписи."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "TEST SELLER"),
        x509.NameAttribute(NameOID.SERIAL_NUMBER, "IIN123456789011"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "BIN123456789021"),
    ])
    now = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(subject).issuer_name(issuer).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=3650))
            .sign(key, hashes.SHA256()))
    blob = pkcs12.serialize_key_and_certificates(
        b"test", key, cert, None,
        serialization.BestAvailableEncryption(pin.encode()))
    with open(path, "wb") as f:
        f.write(blob)


def test_local_ticket_structure():
    x = soap.build_local_auth_ticket("123456789011", ttl_minutes=15)
    root = etree.fromstring(x.encode())
    assert root.tag == "authSign"
    assert root.findtext("iin") == "123456789011"
    assert root.findtext("ttlInMinutes") == "15"
    assert root.findtext("timeMark").isdigit()
    assert root.findtext("state")  # nonce присутствует


def test_sign_ticket_enveloped_self_verifies():
    with tempfile.NamedTemporaryFile(suffix=".p12", delete=False) as f:
        p12 = f.name
    _make_p12(p12, "Qwerty12")
    ticket = soap.build_local_auth_ticket("123456789011")
    signed = soap.sign_auth_ticket(ticket, p12, "Qwerty12")  # бросит, если verify не прошёл
    assert "enveloped-signature" in signed
    # подпись — потомок authSign (enveloped внутрь тикета), а не снаружи
    root = etree.fromstring(signed.encode())
    assert root.tag == "authSign"
    assert root.find("{http://www.w3.org/2000/09/xmldsig#}Signature") is not None


def test_sign_ticket_wrong_pin_fails():
    with tempfile.NamedTemporaryFile(suffix=".p12", delete=False) as f:
        p12 = f.name
    _make_p12(p12, "Qwerty12")
    with pytest.raises(Exception):
        soap.sign_auth_ticket(soap.build_local_auth_ticket("123456789011"), p12, "wrongpin")


def test_wss_header_carries_iin_and_password():
    h = soap._wss_header("040331550432", "p@ss<&>")
    assert "<wsse:Username>040331550432</wsse:Username>" in h
    assert "PasswordText" in h
    assert "p@ss&lt;&amp;&gt;" in h  # пароль экранирован


def test_query_criteria_order_matches_xsd():
    # порядок direction→dateFrom→dateTo→asc→pageNum обязателен (иначе cvc-complex-type)
    import inspect
    src = inspect.getsource(soap.query_invoices)
    order = [src.index(t) for t in ("<direction>", "<dateFrom>", "<dateTo>", "<asc>", "<pageNum>")]
    assert order == sorted(order)
