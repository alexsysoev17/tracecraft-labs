# Local security boundary

Bind to `127.0.0.1` only. Requests require permitted Host/Origin, JSON for mutations, a 64 KiB limit and server-assigned demo scope. Do not expose this app to a network or treat the demo principal as authentication.

Retrieval filters tenant/brand/snapshot/permissions/review before scoring. Source preview and traces enforce scope; cache namespaces include context, permissions, model/prompt/retrieval/source versions. Cache admission and hits revalidate exact source claims. Source instructions never select a tool or expand permissions. Live proposals are checked as untrusted structured data; only allowlisted local tools execute.

Import accepts explicit roots, rejects absolute/traversal/symlink paths, bounds files and totals, verifies referenced hashes, and compares sources before/after. It does not fetch arbitrary URLs or run uploaded HTML. Unreviewed/inferred observations stay unreviewed/inferred. Originals remain untouched.

Never commit `private/`, `runtime/`, weights, original notes, credentials or customer files. Reports are generated from explicit synthetic experiments, not bulk exports of runtime traces. `make privacy-check` checks reports and credential patterns; `scripts/export_public.py` builds an allowlisted review copy. A passing scan is not a guarantee that arbitrary corporate content is safe to publish.

Report a discovered issue through a private channel chosen by the repository owner. Do not include credentials or customer evidence in public issues. No external communication endpoint is configured here.
