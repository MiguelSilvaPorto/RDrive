"""Testes do setup guiado (non-OAuth) — metadados e mapeamento rclone."""

from __future__ import annotations

import unittest

from rdrive.core.cloud.remote_setup import (
    build_guided_rclone_options,
    guided_fields_for_backend,
    setup_mode_for_backend,
    supports_guided_setup,
    validate_guided_answers,
)


class GuidedSetupMetadataTests(unittest.TestCase):
    def test_guided_backends(self) -> None:
        for slug in ("s3", "webdav", "sftp", "ftp", "http", "terabox"):
            self.assertTrue(supports_guided_setup(slug))
            self.assertEqual(setup_mode_for_backend(slug), "guided")
            self.assertTrue(guided_fields_for_backend(slug))

    def test_oauth_mode(self) -> None:
        self.assertEqual(setup_mode_for_backend("drive", oauth_auto=True), "oauth")
        self.assertFalse(supports_guided_setup("drive"))

    def test_manual_mode(self) -> None:
        self.assertEqual(setup_mode_for_backend("b2"), "manual")
        self.assertFalse(supports_guided_setup("b2"))


class GuidedOptionsBuilderTests(unittest.TestCase):
    def test_s3_options_with_endpoint(self) -> None:
        opts = build_guided_rclone_options(
            "s3",
            {
                "access_key": "AKIA",
                "secret": "SECRET",
                "region": "eu-west-1",
                "endpoint": "https://s3.example.com",
            },
        )
        self.assertEqual(opts["access_key_id"], "AKIA")
        self.assertEqual(opts["secret_access_key"], "SECRET")
        self.assertEqual(opts["region"], "eu-west-1")
        self.assertEqual(opts["provider"], "Other")
        self.assertEqual(opts["endpoint"], "https://s3.example.com")

    def test_webdav_options(self) -> None:
        opts = build_guided_rclone_options(
            "webdav",
            {"url": "https://dav.test/", "user": "u", "password": "p"},
        )
        self.assertEqual(opts["url"], "https://dav.test/")
        self.assertEqual(opts["user"], "u")
        self.assertEqual(opts["pass"], "p")

    def test_sftp_key_or_password(self) -> None:
        ok, _ = validate_guided_answers(
            "sftp",
            {"host": "h", "user": "u", "key": "-----BEGIN"},
        )
        self.assertTrue(ok)
        ok, msg = validate_guided_answers("sftp", {"host": "h", "user": "u"})
        self.assertFalse(ok)
        self.assertIn("senha", msg.lower())


if __name__ == "__main__":
    unittest.main()
