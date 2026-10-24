"""Guards on how the stack is wired that no unit test of a single service would catch."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _vars(service: str) -> list[str]:
    text = (ROOT / "scripts" / "dev-up.ps1").read_text(encoding="utf-8")
    block = re.search(rf'"{re.escape(service)}"\s*=\s*@\{{.*?\n(?=\s*"[a-z-]+"\s*=|\}})', text, re.S)
    assert block, f"service {service} not found in dev-up.ps1"
    m = re.search(r"Vars\s*=\s*(.+)", block.group(0))
    assert m, f"no Vars for {service}"
    return re.findall(r'"([A-Z_]+)"', m.group(1))


def test_web_dev_server_gets_the_variables_its_proxy_needs():
    """vite.config.ts injects X-API-Key from CORE_API_KEY; without it every /core/... call was a 401."""
    got = _vars("web")
    assert {"CORE_API_KEY", "CORE_API_URL"} <= set(got)
    assert "REASONING_URL" not in got  # the elder app no longer calls reasoning (it has no auth)


def test_core_api_gets_the_livekit_settings_for_the_token_endpoint():
    got = _vars("core-api")
    assert {"LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "ARJUN_AGENT_NAME"} <= set(got)


def test_the_web_app_uses_no_browser_speech_api():
    """The demo's voice must be Gnani's (CLAUDE.md contest rules): no SpeechRecognition / speechSynthesis."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("check_no_browser_speech", ROOT / "scripts" / "check_no_browser_speech.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.find_hits() == []


def test_the_web_app_never_calls_reasoning_directly():
    """The agent owns every turn; reasoning has no auth and must not be reachable from the browser."""
    for f in (ROOT / "web" / "src").rglob("*.ts*"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        assert "/reasoning" not in text, f"{f.name} calls reasoning"
