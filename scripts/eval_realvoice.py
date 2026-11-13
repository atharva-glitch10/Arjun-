"""Evaluate synthetic/own-voice WAV clips through Prisma REST STT and reasoning /turn.

Input directory: <lang>_<n>.wav clips and labels.csv with expected_lang,
expected_intent, expected_slot columns. A filename column is optional; when
omitted, sorted clips are paired with CSV rows. Slot labels may be plain text
or a JSON object whose key/value pairs must occur in the /turn response.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import os
import re
import sys
import wave
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
VOICE_AGENT = ROOT / "services" / "voice-agent"
LANGUAGE = re.compile(r"^(mr|hi|en|bn|gu|kn|ml|pa|ta|te|or)(?:-|$)", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="directory containing <lang>_<n>.wav and labels.csv")
    parser.add_argument(
        "--user-id", type=int, required=True,
        help="throwaway synthetic user id; /turn can update this user's conversation/action state",
    )
    parser.add_argument(
        "--reasoning-url",
        default=os.environ.get("REASONING_URL", "http://127.0.0.1:8001"),
        help="reasoning service base URL (default: REASONING_URL or localhost:8001)",
    )
    parser.add_argument("--labels", type=Path, help="labels CSV path (default: <folder>/labels.csv)")
    return parser.parse_args()


def language_prefix(value: str) -> str:
    match = LANGUAGE.match(value.strip())
    return match.group(1).lower() if match else value.strip().lower()


def read_labels(path: Path, clips: list[Path]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        required = {"expected_lang", "expected_intent", "expected_slot"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: missing columns: {', '.join(sorted(missing))}")
        rows = list(reader)

    if reader.fieldnames and "filename" in reader.fieldnames:
        by_name = {row["filename"].strip(): row for row in rows}
        missing_clips = [clip.name for clip in clips if clip.name not in by_name]
        if missing_clips:
            raise ValueError(f"{path}: no label row for {', '.join(missing_clips)}")
        return [by_name[clip.name] for clip in clips]
    if len(rows) != len(clips):
        raise ValueError(f"{path}: expected {len(clips)} rows for {len(clips)} clips; found {len(rows)}")
    return rows


def wav_duration(data: bytes) -> float:
    with wave.open(io.BytesIO(data), "rb") as wav:
        if wav.getcomptype() != "NONE" or wav.getsampwidth() != 2 or wav.getnchannels() not in (1, 2):
            raise ValueError("expected uncompressed 16-bit mono/stereo PCM WAV")
        return wav.getnframes() / wav.getframerate()


def slot_matches(expected: str, response: dict[str, Any]) -> bool | None:
    expected = expected.strip()
    if not expected or expected.casefold() in {"-", "n/a", "na"}:
        return None
    try:
        parsed = json.loads(expected)
    except json.JSONDecodeError:
        serialized = json.dumps(response, ensure_ascii=False).casefold()
        return expected.casefold() in serialized
    if isinstance(parsed, dict):
        def find_values(value: Any, key: str) -> list[Any]:
            found = []
            if isinstance(value, dict):
                for child_key, child in value.items():
                    if child_key.casefold() == key.casefold():
                        found.append(child)
                    found.extend(find_values(child, key))
            elif isinstance(value, list):
                for child in value:
                    found.extend(find_values(child, key))
            return found

        return bool(parsed) and all(
            any(str(value).strip().casefold() == str(expected_value).strip().casefold()
                for value in find_values(response, str(key)))
            for key, expected_value in parsed.items()
        )
    return str(parsed).strip().casefold() in json.dumps(response, ensure_ascii=False).casefold()


def failure_cause(*, error: str | None, language_ok: bool | None, intent_ok: bool | None, slot_ok: bool | None) -> str:
    if error:
        return error
    causes = []
    if language_ok is False:
        causes.append("language_mismatch")
    if intent_ok is False:
        causes.append("intent_mismatch")
    if slot_ok is False:
        causes.append("slot_mismatch")
    return ",".join(causes) if causes else "—"


async def evaluate(args: argparse.Namespace) -> int:
    folder = args.folder.resolve()
    labels_path = args.labels or folder / "labels.csv"
    clips = sorted(folder.glob("*.wav"))
    if not clips:
        raise ValueError(f"{folder}: no WAV clips found")
    if any(not re.fullmatch(r"[a-z]{2}_[0-9]+\.wav", clip.name, re.IGNORECASE) for clip in clips):
        raise ValueError("clip names must match <lang>_<n>.wav")
    labels = read_labels(labels_path, clips)
    sys.path.insert(0, str(VOICE_AGENT))
    from prisma_v3 import PrismaV3STT

    stt = PrismaV3STT(transport="rest")
    reasoning_url = args.reasoning_url.rstrip("/") + "/turn"
    print("| Clip | Detected language | Reply language | Intent | Slot correct | Failure cause |")
    print("| --- | --- | --- | --- | --- | --- |")
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            for clip, label in zip(clips, labels, strict=True):
                detected = reply_language = intent = "—"
                slot_ok: bool | None = None
                language_ok: bool | None = None
                intent_ok: bool | None = None
                error = None
                try:
                    audio = clip.read_bytes()
                    seconds = wav_duration(audio)
                except (OSError, ValueError):
                    error = "invalid_wav"
                else:
                    try:
                        text, detected = await stt.transcribe_wav(audio, seconds)
                    except (RuntimeError, httpx.HTTPError):
                        error = stt._rest_recognizer().last_error or "stt_unavailable"
                    except ValueError:
                        error = "unsupported_duration"
                    if not error and not text:
                        error = stt._rest_recognizer().last_error or "empty_transcript"
                    elif not error:
                        try:
                            response = await client.post(
                                reasoning_url,
                                json={"user_id": args.user_id, "text": text, "language_code": detected or None},
                            )
                        except httpx.HTTPError:
                            error = "turn_unreachable"
                        if error:
                            result = {}
                        elif response.status_code != 200:
                            error = f"turn_http_{response.status_code}"
                            result = {}
                        else:
                            result = response.json()
                        if not error:
                            reply_language = str(result.get("language") or "—")
                            intent = str(result.get("intent") or "—")
                            language_ok = language_prefix(detected) == language_prefix(label["expected_lang"])
                            intent_ok = intent.casefold() == label["expected_intent"].strip().casefold()
                            slot_ok = slot_matches(label["expected_slot"], result)
                cause = failure_cause(error=error, language_ok=language_ok, intent_ok=intent_ok, slot_ok=slot_ok)
                slot_display = "n/a" if slot_ok is None else ("yes" if slot_ok else "no")
                print(f"| {clip.name} | {detected or '—'} | {reply_language} | {intent} | {slot_display} | {cause} |")
    finally:
        await stt.aclose()
    return 0


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(evaluate(args))
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        print(f"eval_realvoice: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
