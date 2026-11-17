# Implementation plan

1. Read all three supplied notes and master brief; inspect only the permitted Akella schema. **Done.**
2. Freeze shared contracts and repository boundaries before delegating. **Done.**
3. Build independent complete paths: ATLAS retrieval; RELAY durable execution; SENTINEL comparisons; LENS trace diagnosis; ECHO guarded reuse; CANON brand benchmark. **Done.**
4. Connect six research pages to real local APIs. Prepare independently authored synthetic data and reproducible experiments. **Done.**
5. Run unit, integration, security, browser and restart checks; save measured reports and honest blocked/skipped statuses. **Evidence recorded:** automated/static checks, fresh-checkout fixture bootstrap, six-page browser smoke, process restart and real offline embedding persistence. Refer to [verification](reports/public/verification.json) for the final count and source rather than a hardcoded total. Original CANON is now 32/32; the withheld follow-up challenge remains 7/12. Live evaluation was not run.
6. Run separate engineering/security review and frozen source-based challenges. **Recorded:** nine engineering findings repaired and rechecked; first disclosed quality set 20/23 → 23/23 with three unscored cases; withheld follow-up 7/12 → 7/12. Preserve failures and review phases in [independent quality](reports/public/independent-quality.json), [security](reports/public/independent-security.json) and [implementation review](reports/public/independent-review.json).
7. Audit public export and deliver commands, results and limits. The initial delivery was local only. A later explicit user approval authorized public GitHub publication; no application deployment is requested. **Review copy:** `dist/public-review-audited` (the earlier `dist/public-review` remains a historical snapshot); audit and delivered measurements are recorded in `reports/public`.

The supplied notes are design sources, not current library documentation. Note 1 summarizes a book; notes 2 and 3 are the note author's interpretations. Full originals remain outside this repository.

## Ownership and decisions

The integrator owns shared contracts, SQLite schema, dependencies, API integration and final reports. Module owners use the frozen contracts in `docs/contracts.md`. The stack is Python 3.12, FastAPI/Pydantic, SQLite FTS5 and an optional real CPU embedding encoder. A small native web UI avoids a separate frontend dependency runtime. ADR 001 explains embedded vectors and durable workflow without Qdrant/LangGraph.

## Initial source inspection

Akella schema was inspected read-only at revision `2909d1d94f0cbe94886a875acfcdc83b643604ee` (working tree dirty). No STC directory found in the permitted brand store. Status: **MISSING_PRIVATE_SOURCE**. Other private brand content was not imported.
