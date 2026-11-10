"""Authenticator codes and recovery codes. No database and no Flask app."""

from services import second_factor, totp


def test_rfc6238_sha1_vectors():
    key = b'12345678901234567890'
    assert totp.hotp(key, 59 // 30) == '287082'
    assert totp.hotp(key, 1111111109 // 30) == '081804'
    assert totp.hotp(key, 1234567890 // 30) == '005924'


def test_generated_secret_verifies_once_inside_the_window():
    secret = totp.generate_secret()
    key = totp.decode_secret(secret)
    now = 1_700_000_000
    counter = now // 30
    code = totp.hotp(key, counter)
    previous = totp.hotp(key, counter - 1)
    assert totp.matching_step(secret, code, now) == counter
    assert totp.matching_step(secret, previous, now) == counter - 1
    assert totp.matching_step(secret, code, now, last_step=counter) is None
    used = {totp.hotp(key, counter + offset) for offset in (-1, 0, 1)}
    wrong = next(item for item in ('000000', '111111', '222222', '333333') if item not in used)
    assert totp.matching_step(secret, wrong, now) is None


def test_otpauth_uri_is_time_based():
    uri = totp.otpauth_uri('ABCDEFGHIJKLMNOP', 'ada', 'College')
    assert uri.startswith('otpauth://totp/')
    assert 'secret=ABCDEFGHIJKLMNOP' in uri
    assert 'digits=6' in uri
    assert 'period=30' in uri
    assert totp.account_name('ada:extra') == 'adaextra'


def test_recovery_code_matches_once_when_the_caller_keeps_the_remainder():
    codes = totp.new_recovery_codes()
    assert len(codes) == 8
    assert len(set(codes)) == 8
    hashes = totp.hash_recovery([codes[0]])
    kept = totp.match_recovery(hashes, codes[0].replace('-', '').lower())
    assert kept == []
    assert totp.match_recovery(kept, codes[0]) is None
    assert totp.match_recovery(hashes, 'ZZZZ-ZZZZ') is None


def test_requirement_and_provider_mfa():
    assert second_factor.role_requires('optional', 'Super Admin') is False
    assert second_factor.role_requires('staff', 'HOD') is True
    assert second_factor.role_requires('staff', 'Teacher') is False
    assert second_factor.role_requires('everyone', 'Student') is True
    assert second_factor.idp_asserts_mfa({'amr': ['pwd', 'otp']}) is True
    assert second_factor.idp_asserts_mfa({'amr': ['pwd']}) is False
    assert second_factor.idp_asserts_mfa({'acr': 'urn:mfa'}) is True
    assert second_factor.idp_asserts_mfa({}) is False


def test_prepare_does_not_query_when_the_feature_is_off():
    class _Boom:
        def execute(self, *_args, **_kwargs):
            raise AssertionError('second factor queried the database while off')

    assert second_factor.prepare(_Boom(), {'id': 1, 'role': 'Admin'}, 'ada') is None
