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
    assert {"CORE_API_KEY", "CORE_API_URL", "REASONING_URL"} <= set(got)


def test_core_api_gets_the_livekit_settings_for_the_token_endpoint():
    got = _vars("core-api")
    assert {"LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "ARJUN_AGENT_NAME"} <= set(got)
