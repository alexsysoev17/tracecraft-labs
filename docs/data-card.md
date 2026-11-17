# Public demo data card

**Origin:** original synthetic documents authored specifically for TRACECRAFT LABS. Names: Luma Field (`luma`) and Veyra Works (`veyra`). These are fictional demonstration brands, with no relationship to STC or other client materials.

**Contents:** 28 evidence records in four versioned source documents; 32 RU/EN evaluation cases; six answer-cache validation pairs. Record categories include explicit rules, observed examples, negative examples, review status, linked exception, unresolved rule conflict and a synthetically restricted record for access tests. Historical v1 rules are available only in v1 scope. Source hashes and section/character offsets link each record to the original synthetic Markdown.

**Annotation:** machine-authored and source-checked, not expert-reviewed. Evidence IDs/spans and permissible claims form gold. Public splits are by scenario family; they are not secret holdouts. File `build_dataset.py` regenerates the source documents, corpus and gold deterministically. Cache validation data is a separate tiny authored sample.

**Excluded:** supplied book notes, original book PDF, client brandbooks, Akella datasets, images/fonts, private traces, embeddings and model weights. A fake restricted source in public demo data tests the application's access boundary; its contents are not an actual secret.

**Intended use:** reproducible investigation of mechanics and observable failure modes. Not intended for estimating reliability on real clients, comparing commercial model quality, or certifying design/brand compliance.

**Private-source status:** MISSING_PRIVATE_SOURCE for STC. A read-only compatible importer exists and is tested against independently created Akella-contract fixtures. No actual STC source was imported or verified.

**Additional source-first challenges:** the preserved [independent quality report](../reports/public/independent-quality.json) contains a separate 26-case set (23 scored, three uncertain) and a later 12-case challenge withheld from the implementer until final code freeze. These do not enter the original 32-case gold or retrieval corpus. They remain small machine-authored samples without expert certification; disclosed versus withheld phases are labeled separately.
