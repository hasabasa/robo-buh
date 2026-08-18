"""Тест-харнесс контура ЭЦП: полный цикл sign → verify через NCANode, без боевых ключей.

Генерирует одноразовый тестовый p12 (RSA + keyUsage + extendedKeyUsage) через openssl,
подписывает им XML декларации через NCANode /xml/sign (эмулируя то, что в проде делает
NCALayer на машине клиента), затем проверяет через /xml/verify и разбор SignerInfo.

Боевые ключи НУЦ здесь не используются — это структурный тест плумбинга. Реальная цепочка
НУЦ (valid=true) проверяется отдельно, на настоящей ЭЦП. Тест требует запущенный NCANode
(NCANODE_URL) и openssl; при недоступности — skip.

Примечание: p12 генерим openssl'ом, а не cryptography — NCANode v3 отвергает EKU-кодировку
из cryptography.pkcs12 (verify → 500 getExtendedKeyUsage null), а openssl-cert принимает.
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import tempfile

import httpx
import pytest

from app.signing.ncanode import NCANodeClient

NCANODE_URL = os.environ.get("NCANODE_URL", "http://ncanode:14579")
TEST_PASSWORD = "test123"
SAMPLE_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<declaration formCode="910.00"><taxpayer bin="260440029440"/><amount>338000</amount></declaration>'
)

_OPENSSL_CNF = """
[req]
distinguished_name = dn
x509_extensions = v3
prompt = no
[dn]
CN = TEST TESTOV
serialNumber = IIN900101300123
O = TOO CS
[v3]
keyUsage = critical, digitalSignature, nonRepudiation
extendedKeyUsage = clientAuth, emailProtection
basicConstraints = CA:FALSE
"""


def _make_test_p12_b64() -> str:
    """Одноразовый RSA-p12 (openssl) с keyUsage+EKU; ИИН в serialNumber субъекта."""
    d = tempfile.mkdtemp()
    try:
        cnf, key, crt, p12 = (os.path.join(d, f) for f in ("t.cnf", "k.pem", "c.pem", "t.p12"))
        with open(cnf, "w") as f:
            f.write(_OPENSSL_CNF)
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", key,
                        "-out", crt, "-days", "365", "-nodes", "-config", cnf],
                       check=True, capture_output=True)
        subprocess.run(["openssl", "pkcs12", "-export", "-out", p12, "-inkey", key, "-in", crt,
                        "-passout", f"pass:{TEST_PASSWORD}"], check=True, capture_output=True)
        return base64.b64encode(open(p12, "rb").read()).decode()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _ncanode_up() -> bool:
    try:
        return httpx.get(f"{NCANODE_URL}/actuator/health", timeout=5).status_code == 200
    except Exception:
        return False


_SKIP = not (_ncanode_up() and shutil.which("openssl"))


@pytest.mark.skipif(_SKIP, reason="нужен запущенный NCANode и openssl")
@pytest.mark.asyncio
async def test_sign_then_verify_roundtrip():
    client = NCANodeClient(base_url=NCANODE_URL)
    p12 = _make_test_p12_b64()

    # 1. Подписываем (в проде это делает NCALayer у клиента)
    signed = await client.sign_xml(SAMPLE_XML, p12, TEST_PASSWORD)
    assert "Signature" in signed, "в результате нет ds:Signature"

    # 2. Верифицируем и разбираем подписанта
    signers = await client.verify_xml(signed)
    assert signers, "verify не вернул подписантов"
    s = signers[0]
    # valid=False ожидаемо: самоподписанный тест-серт вне цепочки НУЦ. Плумбинг проверяем на
    # том, что структура разобралась и блок подписи присутствует.
    assert s.serial_number, "не разобрали серийный номер сертификата"
    assert s.raw.get("signature"), "нет блока подписи в ответе verify"
