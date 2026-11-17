# Local API

Run `make serve`. OpenAPI is available as JSON at `/openapi.json`; the committed `docs/openapi.json` is generated from the actual application. The web client is on the same origin, with no CORS wildcard. Extra request fields are rejected.

Core routes are documented in [contracts.md](contracts.md). In addition, `/api/status` reports actual local encoder availability. `/api/reports/{module}?mode=fixture|local` reads recorded reports. POST `/api/experiments/{module}` runs that isolated synthetic scenario. Requests with `mode=live` do not trigger a provider from the browser. No path-based file upload or URL-fetch route exists.

RELAY state/artifacts are reloaded with the saved run ID. `approve` needs both `artifact_hash` and `input_hash`; mismatches fail. `/api/runs/{id}` returns recorded spans and mode `replay`. Tool proposals are not executable HTTP endpoints. Brand/snapshot controls select only the two public demo brands, not a user-controlled tenant identity.

Example (server running):

```sh
curl -s http://127.0.0.1:8317/api/atlas \
  -H 'Content-Type: application/json' \
  -d '{"query":"LF-MOSS-42","brand":"luma","snapshot":"v2","mode":"local"}'
```
