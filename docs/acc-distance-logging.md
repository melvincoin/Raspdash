# ACC / Front Assist distance logging

This experimental read-only logger polls one known module 13 DID per UDS cycle while the 15-minute ride window is active.

Candidates: `102E`, `1011`, `1012`, `1065`, `1880`. After three unsupported/timeout results, a DID is skipped for the rest of that ride.

Logs are written to `data/ride_logs/acc_distance/acc-distance-YYYYMMDD-HHMMSS.jsonl`. No dashboard widget or warning is enabled.

Add an optional marker:

```text
GET /api/log/marker?label=voorligger
GET /api/log/marker?label=dicht_op_voorligger
GET /api/log/marker?label=acc_aan
GET /api/log/marker?label=acc_uit
GET /api/log/marker?label=front_assist_vermoeden
```

Analyze a completed ride:

```bash
python scripts/analyze_acc_distance_log.py data/ride_logs/acc_distance/<log>.jsonl
```

The resulting report lists response statuses, changing payload bytes and samples nearest to each marker. Results remain experimental until correlated with known vehicle behavior.
