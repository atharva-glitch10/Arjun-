"""Unit tests for scripts/tunnel_url.py (standard-library unittest; pytest also collects them)."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import tunnel_url  # noqa: E402

URL = "https://calm-river-1234.trycloudflare.com"


class FindUrlTests(unittest.TestCase):
    def test_finds_the_quick_tunnel_url_in_cloudflared_output(self):
        log = (
            "\x1b[0m2026-11-03T10:00:00Z INF Thank you for trying Cloudflare Tunnel.\r\n"
            "|  https://calm-river-1234.trycloudflare.com  |\r\n"
            "2026-11-03T10:00:01Z INF Registered tunnel connection\r\n"
        )
        self.assertEqual(tunnel_url.find_url(log), URL)

    def test_ignores_cloudflare_documentation_links(self):
        log = "See https://developers.cloudflare.com/cloudflare-one/ for help.\n"
        self.assertIsNone(tunnel_url.find_url(log))

    def test_returns_none_for_an_empty_log(self):
        self.assertIsNone(tunnel_url.find_url(""))

    def test_returns_the_first_url_when_the_log_has_two(self):
        second = "https://other-name-9999.trycloudflare.com"
        self.assertEqual(tunnel_url.find_url(f"{URL}\n{second}\n"), URL)


class ReplaceBaseUrlTests(unittest.TestCase):
    def test_replaces_the_line_and_keeps_every_other_byte(self):
        text = (
            "# comment\r\n"
            "CORE_API_KEY=secret\r\n"
            "BASE_URL=http://localhost:5173\r\n"
            "JOIN_SECRET=\r\n"
        )
        expected = (
            "# comment\r\n"
            "CORE_API_KEY=secret\r\n"
            f"BASE_URL={URL}\r\n"
            "JOIN_SECRET=\r\n"
        )
        self.assertEqual(tunnel_url.replace_base_url(text, URL), expected)

    def test_replaces_an_empty_value_and_preserves_spacing(self):
        self.assertEqual(
            tunnel_url.replace_base_url("BASE_URL = \nNEXT=1\n", URL),
            f"BASE_URL = {URL}\nNEXT=1\n",
        )

    def test_leaves_a_commented_example_alone(self):
        text = "# BASE_URL=http://example\nBASE_URL=http://old\n"
        self.assertEqual(
            tunnel_url.replace_base_url(text, URL),
            f"# BASE_URL=http://example\nBASE_URL={URL}\n",
        )

    def test_replaces_every_active_line_so_dotenv_last_wins_cannot_undo_it(self):
        text = "BASE_URL=http://one\nBASE_URL=http://two\n"
        self.assertEqual(
            tunnel_url.replace_base_url(text, URL),
            f"BASE_URL={URL}\nBASE_URL={URL}\n",
        )

    def test_appends_a_line_when_missing_and_keeps_crlf(self):
        text = "A=1\r\nB=2"
        self.assertEqual(
            tunnel_url.replace_base_url(text, URL),
            f"A=1\r\nB=2\r\nBASE_URL={URL}\r\n",
        )

    def test_appends_to_an_empty_file(self):
        self.assertEqual(tunnel_url.replace_base_url("", URL), f"BASE_URL={URL}\n")

    def test_rejects_a_url_that_is_not_a_quick_tunnel(self):
        with self.assertRaises(ValueError):
            tunnel_url.replace_base_url("BASE_URL=\n", "https://example.com")


class FileAndCliTests(unittest.TestCase):
    def test_wait_reads_an_existing_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "tunnel.log"
            log.write_text(f"starting\n{URL}\n", encoding="utf-8")
            self.assertEqual(tunnel_url.wait_for_url(log, timeout=0.1, interval=0.05), URL)

    def test_reads_the_utf16_log_windows_tee_object_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "tunnel.log"
            log.write_bytes(f"starting\r\n{URL}\r\n".encode("utf-16"))
            self.assertEqual(tunnel_url.wait_for_url(log, timeout=0.1, interval=0.05), URL)

    def test_set_base_url_cli_writes_only_that_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            original = b"CORE_API_KEY=secret\r\nBASE_URL=old\r\nX=1\r\n"
            env.write_bytes(original)
            self.assertEqual(tunnel_url.main(["set-base-url", str(env), URL]), 0)
            self.assertEqual(
                env.read_bytes(),
                b"CORE_API_KEY=secret\r\n" + f"BASE_URL={URL}\r\n".encode() + b"X=1\r\n",
            )

    def test_find_cli_prints_the_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "tunnel.log"
            log.write_text(f"noise\n{URL}\n", encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(tunnel_url.main(["find", str(log)]), 0)
            self.assertEqual(out.getvalue().strip(), URL)

    def test_find_cli_returns_nonzero_without_a_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "tunnel.log"
            log.write_text("still connecting\n", encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(tunnel_url.main(["find", str(log)]), 1)


if __name__ == "__main__":
    unittest.main()
