from dataclasses import asdict, replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from wordloom.config import ConfigError, ConfigStore, Profile, Settings, normalize_url
from wordloom.platforms.credentials import Credentials, CredentialError


class Vault:
    def __init__(self):
        self.values = {}

    def get_password(self, service, account):
        return self.values.get((service, account))

    def set_password(self, service, account, value):
        self.values[service, account] = value

    def delete_password(self, service, account):
        self.values.pop((service, account), None)


class ConfigTests(unittest.TestCase):
    def profile(self, **kw):
        return Profile(base_url="https://provider.example/v1/", model="custom-model", **kw)

    def test_profiles_roundtrip_switch_delete_and_separate_ocr(self):
        with TemporaryDirectory() as d:
            store = ConfigStore(Path(d))
            self.assertEqual(store.load().profiles, [])
            p, q, o = self.profile(), self.profile(name="第二个"), self.profile(purpose="ocr", vision=True)
            s = Settings()
            for item in (p, q, o):
                s.upsert(item)
            s.active_translation = q.id
            store.save(s)
            loaded = store.load()
            self.assertEqual(loaded.active().id, q.id)
            self.assertEqual(loaded.active("ocr").id, o.id)
            loaded.remove(q.id)
            store.save(loaded)
            self.assertEqual(store.load().active().id, p.id)
            self.assertEqual(p.base_url, "https://provider.example/v1")

    def test_secret_never_in_plain_config(self):
        with TemporaryDirectory() as d:
            p = self.profile()
            vault = Vault()
            creds = Credentials(vault)
            creds.set(p.credential_id, "test-secret-not-real")
            store = ConfigStore(Path(d))
            store.save(Settings([p], p.id))
            saved = store.path.read_text(encoding="utf-8")
            self.assertNotIn("test-secret-not-real", saved)
            self.assertNotIn("api_key", saved)
            self.assertEqual(creds.get(p.credential_id), "test-secret-not-real")
            self.assertNotEqual(replace(p, base_url="https://different.example/v1").credential_id, p.credential_id)
            self.assertNotEqual(replace(p, purpose="ocr").credential_id, p.credential_id)

    def test_invalid_urls(self):
        for value in ["http://remote.example/v1", "file:///tmp/key", "https://user:secret@x/v1", "https://x/v1?api_key=secret", "https://x/v1#secret", "https://x/v1\nheader", "https://x/v1/chat/completions", "https://x:bad/v1", "https://x/a b"]:
            with self.subTest(value=value), self.assertRaises(ConfigError):
                normalize_url(value)
        self.assertEqual(normalize_url("http://127.0.0.1:8000/v1/"), "http://127.0.0.1:8000/v1")

    def test_parameter_validation(self):
        for updates in [dict(timeout=0), dict(timeout=float("nan")), dict(temperature=float("inf")), dict(max_tokens=True), dict(stream="yes"), dict(protocol="not-supported"), dict(prompts={}), dict(model="")]:
            with self.subTest(updates=updates), self.assertRaises(ConfigError):
                replace(self.profile(), **updates).validate()
        p = replace(self.profile(), temperature=None, max_tokens=None)
        p.validate()

    def test_corrupt_config_kept(self):
        with TemporaryDirectory() as d:
            store = ConfigStore(Path(d))
            for bad in ['{broken', json.dumps({"schema": 999}), '[]']:
                store.path.write_text(bad, encoding="utf-8")
                with self.assertRaises(ConfigError):
                    store.load()
                self.assertEqual(store.path.read_text(encoding="utf-8"), bad)

    def test_atomic_validation_keeps_previous_config(self):
        with TemporaryDirectory() as d:
            store = ConfigStore(Path(d))
            good = Settings([self.profile()])
            store.save(good)
            old = store.path.read_bytes()
            good.profiles[0].model = ""
            with self.assertRaises(ConfigError):
                store.save(good)
            self.assertEqual(store.path.read_bytes(), old)

    def test_session_credentials_explicit_and_clear(self):
        c = Credentials()
        with self.assertRaises(CredentialError):
            c.set("a", "secret")
        c.set("a", "secret", session_only=True)
        self.assertEqual(c.get("a"), "secret")
        c.clear_session()
        self.assertEqual(c.get("a"), "")
        with self.assertRaises(CredentialError):
            c.set("a", "a\nb", session_only=True)

    def test_vault_failure_does_not_echo_secrets_or_fallback(self):
        class Broken(Vault):
            def set_password(self, *args):
                raise RuntimeError("test-secret-not-real")
        c = Credentials(Broken())
        with self.assertRaises(CredentialError) as cm:
            c.set("a", "test-secret-not-real")
        self.assertNotIn("test-secret-not-real", str(cm.exception))
        self.assertEqual(c.get("a"), "")

    def test_native_delete_and_session_override(self):
        c = Credentials(Vault())
        c.set("a", "original")
        c.set("a", "temporary", session_only=True)
        self.assertEqual(c.get("a"), "temporary")
        c.clear_session()
        self.assertEqual(c.get("a"), "original")
        c.delete("a")
        self.assertEqual(c.get("a"), "")
