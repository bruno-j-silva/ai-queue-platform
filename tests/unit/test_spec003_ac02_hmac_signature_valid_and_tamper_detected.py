"""SPEC-003/AC-02: canonical HMAC-SHA256 webhook signatures."""

from shared.webhooks.signing import build_headers, sign_payload, verify_signature


def test_spec003_ac02_hmac_signature_valid_and_tamper_detected() -> None:
    body = b'{"event":"job.succeeded","text":"ol\xc3\xa1"}'
    secret = "whsec_test"
    timestamp = 1_720_180_800

    signature = sign_payload(secret, timestamp, body)
    headers = build_headers("delivery-1", 2, timestamp, signature)

    assert headers == {
        "X-Delivery-Id": "delivery-1",
        "X-Timestamp": str(timestamp),
        "X-Attempt": "2",
        "X-Signature": signature,
        "Content-Type": "application/json",
    }
    assert signature.startswith("sha256=")
    assert verify_signature(secret, timestamp, body, signature)
    assert not verify_signature(secret, timestamp, body + b" ", signature)
    assert not verify_signature(secret, timestamp + 1, body, signature)
