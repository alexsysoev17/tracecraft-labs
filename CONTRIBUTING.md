# Contributing

Read AGENTS.md and docs/contracts.md. Keep module contracts versioned; migrations/dependencies have one integrator. Write a failing scenario for a real defect, separate development cases from public test families, and preserve old measured outputs when making comparative claims. Never change gold just to accept current behavior.

Use `make test`, `make check`, `make privacy-check` and the affected module experiment. Real model smoke runs are separate from offline fixture CI. Any live run needs explicit model/key/budget and authorization. Explain which factor changed and retain unsuccessful cases. Do not copy source notes, private brand data or upstream code without required permission/notices.
