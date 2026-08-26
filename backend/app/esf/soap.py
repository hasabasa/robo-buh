"""SOAP-транспорт ЭСФ (ИС ЭСФ КГД): версия API, авторизация сессии, чтение счетов.

Последовательность авторизации (сверено по SDK ЭСФ, SoapUI-проект):
  1. AuthService/createAuthTicket(iin)      → authTicketXml (сервер сам ставит state+timeMark)
  2. клиент подписывает тикет своей ЭЦП     → enveloped-XMLDSIG внутри <authSign>
  3. SessionService/createSessionSigned(...) → sessionId

В ПРОДЕ шаг 2 делает клиент через NCALayer (GOST, ключ не покидает клиента). На тест-стенде
подписываем RSA тест-сертом (AUTH_RSA256_SELLER_NEW.p12) через signxml — бэкенд боевых ключей
не держит. `tin` = БИН предприятия, за которое действуем → мультитенант (один серт за разные БИН).

Стенды: тест `https://test3.esf.kgd.gov.kz:8443/esf-web/ws/api1/`, прод `https://esf.gov.kz:8443/...`.
"""

from __future__ import annotations

import logging
import secrets
import ssl
import urllib.request
from dataclasses import dataclass

from lxml import etree

logger = logging.getLogger(__name__)

TEST_BASE = "https://test3.esf.kgd.gov.kz:8443/esf-web/ws/api1"
PROD_BASE = "https://esf.gov.kz:8443/esf-web/ws/api1"

SOAPENV = "http://schemas.xmlsoap.org/soap/envelope/"
ESF_NS = "esf"  # targetNamespace всех сервисов ЭСФ
C14N_INCLUSIVE = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315#WithComments"  # как в примерах SDK
WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
PWTEXT = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordText"


def _wss_header(iin: str, password: str) -> str:
    """wsse:Security / UsernameToken (Username=ИИН, Password=пароль КАБИНЕТА ЭСФ, не PIN ключа).

    Нужен ТОЛЬКО для createSessionSigned и closeSession; queryInvoice* его не требуют
    (проверено вживую на esf.gov.kz 26.08.2026)."""
    from xml.sax.saxutils import escape
    return (f'<wsse:Security soapenv:mustUnderstand="1" xmlns:wsse="{WSSE}">'
            f"<wsse:UsernameToken><wsse:Username>{iin}</wsse:Username>"
            f'<wsse:Password Type="{PWTEXT}">{escape(password)}</wsse:Password>'
            f"</wsse:UsernameToken></wsse:Security>")


class EsfFault(RuntimeError):
    """SOAP Fault от стенда ЭСФ."""


@dataclass
class EsfSession:
    session_id: str
    tin: str


# ─────────────────────────── низкий уровень: POST ───────────────────────────

def _envelope(body_xml: str, header_xml: str = "") -> bytes:
    return (
        f'<soapenv:Envelope xmlns:soapenv="{SOAPENV}" xmlns:esf="{ESF_NS}">'
        f"<soapenv:Header>{header_xml}</soapenv:Header>"
        f"<soapenv:Body>{body_xml}</soapenv:Body>"
        "</soapenv:Envelope>"
    ).encode("utf-8")


def _post(base: str, service: str, body_xml: str, action: str = "", header_xml: str = "",
          timeout: float = 30.0, verify_tls: bool = True) -> etree._Element:
    """POST SOAP-конверт на {base}/{service}. Возвращает корень ответа или бросает EsfFault."""
    url = f"{base}/{service}"
    data = _envelope(body_xml, header_xml)
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": f'"{action}"',
    })
    ctx = None if verify_tls else ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raw = e.read()  # SOAP Fault приходит с кодом 500 — тело нужно разобрать
    if not raw.strip():
        raise EsfFault(f"{service}: пустой ответ (проверь имя элемента/заголовок)")
    root = etree.fromstring(raw)
    fault = root.find(f".//{{{SOAPENV}}}Fault")
    if fault is not None:
        fs = fault.findtext("faultstring") or fault.findtext(f"{{{SOAPENV}}}Reason")
        raise EsfFault(fs or etree.tostring(fault, encoding="unicode")[:500])
    return root


def _first_text(root: etree._Element, local_name: str) -> str | None:
    r = root.xpath("//*[local-name()=$n]", n=local_name)
    return r[0].text if r and r[0].text else None


# ─────────────────────────── операции ───────────────────────────

def get_esf_version(base: str = TEST_BASE, **kw) -> str | None:
    """Безавторизационный пробник транспорта: версия ИС ЭСФ."""
    root = _post(base, "VersionService", "<esf:esfVersionRequest/>", action="", **kw)
    return _first_text(root, "version") or etree.tostring(root, encoding="unicode")[:300]


def create_auth_ticket(iin: str, base: str = TEST_BASE, **kw) -> str:
    """Шаг 1: сервер выдаёт неподписанный authTicketXml (со своим state+timeMark)."""
    root = _post(base, "AuthService",
                 f"<esf:createAuthTicketRequest><iin>{iin}</iin></esf:createAuthTicketRequest>",
                 action="esf/AuthService/createAuthTicket", **kw)
    ticket = _first_text(root, "authTicketXml")
    if not ticket:
        raise EsfFault("createAuthTicket не вернул authTicketXml")
    return ticket


def build_local_auth_ticket(iin: str, ttl_minutes: int = 15) -> str:
    """Фолбэк, если стенд не отдаёт ticket: собрать <authSign> локально (state генерим сами)."""
    time_mark = _now_ms()
    state = secrets.token_urlsafe(32)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            f"<authSign><timeMark>{time_mark}</timeMark><state>{state}</state>"
            f"<iin>{iin}</iin><ttlInMinutes>{ttl_minutes}</ttlInMinutes></authSign>")


def _now_ms() -> int:
    # обёртка ради тестируемости (monkeypatch); в проде — реальное время
    import time
    return int(time.time() * 1000)


def sign_auth_ticket(ticket_xml: str, p12_path: str, p12_pin: str) -> str:
    """Шаг 2: enveloped-XMLDSIG над <authSign> тест-сертом RSA. Подпись самопроверяется.

    Боевые GOST-ключи так не подписываются (только NCALayer/Kalkan) — этот путь только для
    тест-стенда с RSA-сертом. Пин в логи не пишем.
    """
    from cryptography.hazmat.primitives.serialization import (Encoding, NoEncryption,
                                                              PrivateFormat, pkcs12)
    from signxml import XMLSigner, XMLVerifier

    key, cert, _ = pkcs12.load_key_and_certificates(
        open(p12_path, "rb").read(), p12_pin.encode())
    key_pem = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    cert_pem = cert.public_bytes(Encoding.PEM)

    # убрать XML-декларацию — signxml принимает элемент
    root = etree.fromstring(ticket_xml.encode("utf-8") if isinstance(ticket_xml, str) else ticket_xml)
    signer = XMLSigner(method=__import__("signxml").methods.enveloped,
                       signature_algorithm="rsa-sha256",
                       digest_algorithm="sha256",
                       c14n_algorithm=C14N_INCLUSIVE)
    signed = signer.sign(root, key=key_pem, cert=cert_pem)
    # самопроверка подписи. Тест-серты SDK просрочены (действуют до 2019) — верифицируем на
    # момент внутри срока действия серта, иначе проверяется только истёкший срок, а не крипта.
    from signxml import SignatureConfiguration
    vtime = cert.not_valid_before_utc if hasattr(cert, "not_valid_before_utc") else cert.not_valid_before
    XMLVerifier().verify(signed, x509_cert=cert_pem,
                         expect_config=SignatureConfiguration(verification_time=vtime))
    return etree.tostring(signed, encoding="unicode")


def create_session_signed(tin: str, iin: str, account_password: str, signed_ticket_xml: str,
                          base: str = TEST_BASE, business_profile: str = "ADMIN_ENTERPRISE",
                          source_type: str = "OTHER", **kw) -> EsfSession:
    """Шаг 3: открыть сессию подписанным тикетом → sessionId. Нужен wsse:UsernameToken
    (Username=ИИН, Password=пароль КАБИНЕТА ЭСФ) — иначе `security error verifying the message`."""
    from xml.sax.saxutils import escape
    body = (f"<esf:createSessionSignedRequest><tin>{tin}</tin>"
            f"<businessProfileType>{business_profile}</businessProfileType>"
            f"<signedAuthTicket>{escape(signed_ticket_xml)}</signedAuthTicket>"
            f"<sourceType>{source_type}</sourceType></esf:createSessionSignedRequest>")
    root = _post(base, "SessionService", body, action="esf/SessionService/createSessionSigned",
                 header_xml=_wss_header(iin, account_password), **kw)
    sid = _first_text(root, "sessionId")
    if not sid:
        raise EsfFault("createSessionSigned не вернул sessionId: " +
                       etree.tostring(root, encoding="unicode")[:300])
    return EsfSession(session_id=sid, tin=tin)


def open_session(tin: str, iin: str, account_password: str, sign_fn, base: str = TEST_BASE,
                 **kw) -> EsfSession:
    """Полный вход: createAuthTicket → sign_fn(тикет) → createSessionSigned.

    sign_fn(ticket_xml)->signed_xml инъектируется: в ПРОДЕ это подпись клиента через NCALayer
    (ключ у клиента), в тестах — `sign_auth_ticket` с RSA-сертом SDK. Пароль кабинета отдельно
    от подписи — он идёт в UsernameToken, а не в ключ."""
    ticket = create_auth_ticket(iin, base=base, **kw)
    signed = sign_fn(ticket)
    return create_session_signed(tin, iin, account_password, signed, base=base, **kw)


def query_invoices(session: EsfSession, direction: str, date_from: str, date_to: str,
                   page: int = 1, base: str = TEST_BASE, **kw) -> list[dict]:
    """Список счетов за период (≤1 квартала!). direction: OUTBOUND (выданные) / INBOUND (полученные).

    Порядок элементов criteria строгий по XSD: direction, dateFrom, dateTo, asc, pageNum.
    Даты в ISO 'ГГГГ-ММ-ДДTчч:мм:сс'. Заголовок UsernameToken тут НЕ нужен."""
    crit = (f"<criteria><direction>{direction}</direction>"
            f"<dateFrom>{date_from}</dateFrom><dateTo>{date_to}</dateTo>"
            f"<asc>false</asc><pageNum>{page}</pageNum></criteria>")
    root = _post(base, "InvoiceService",
                 f"<esf:queryInvoiceRequest><sessionId>{session.session_id}</sessionId>{crit}</esf:queryInvoiceRequest>",
                 **kw)
    out = []
    for it in root.xpath("//*[local-name()='invoiceInfoList']/*"):
        out.append({etree.QName(c).localname: (c.text or "").strip() for c in it})
    return out


def query_invoice_by_id(session: EsfSession, ids: list[str], base: str = TEST_BASE,
                        **kw) -> etree._Element:
    """Полные счета по id (invoiceContainer) → скармливать parse_esf_invoices."""
    id_xml = "".join(f"<id>{i}</id>" for i in ids)
    return _post(base, "InvoiceService",
                 f"<esf:queryInvoiceByIdRequest><sessionId>{session.session_id}</sessionId>"
                 f"<idList>{id_xml}</idList></esf:queryInvoiceByIdRequest>", **kw)


def close_session(session: EsfSession, iin: str, account_password: str,
                  base: str = TEST_BASE, **kw) -> None:
    _post(base, "SessionService",
          f"<esf:closeSessionRequest><sessionId>{session.session_id}</sessionId></esf:closeSessionRequest>",
          action="esf/SessionService/closeSession", header_xml=_wss_header(iin, account_password), **kw)
