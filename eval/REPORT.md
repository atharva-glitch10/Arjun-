# Arjun system evaluation report

Generated: 2026-11-07 12:47 UTC

Synthetic text regression sets and the local voice turnlog are reported below. No Prisma WER is reported; it is not measured here and publication is restricted by the project policy.

## Intent and language

- Intent accuracy: 50/50 (100.0%).
- Reminder date/time slots: 12/12.
- Mixed Latin + Devanagari cases: 1/1 (small synthetic subset).

## Safety and readings

- Emergency recall: 87/87.
- Emergency false alarms: 0/12.
- BP parsing: 10/10 synthetic accept/reject cases.
- Sugar parsing: not implemented; no numerical sugar-reading parser is scored.

## Dialogue memory

Stored judged dialogue set: 15 scored dialogues from `dialogues_final1.json`; dimensions use a 0–2 scale except safety (0–1).

| Dimension | Mean |
|---|---:|
| remembers context | 1.80 |
| uses her life | 1.47 |
| smart answer | 1.80 |
| natural | 1.93 |
| not repetitive | 1.67 |
| safe | 1.00 |

## Voice latency (last 24 hours)

| Stage | n | p50 ms | p90 ms |
|---|---:|---:|---:|
| EOS → final (STT) | 98 | 673 | 784 |
| Final → reasoning start | 112 | 160 | 980 |
| Reasoning done → first audio | 97 | 656 | 869 |
| EOS → speaking | 81 | 4516 | 6280 |
| Barge-in start → agent stopped | 0 | n/a | n/a |

- Completed voice turns: 81/128; barge-ins at or below 300 ms: 0/0.
- Latency values are n/a where the current local turnlog has no samples; no values are inferred.
