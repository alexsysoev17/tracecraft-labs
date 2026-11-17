# Inspiration and implementation provenance

Inspected on 2026-11-17. TRACECRAFT is an independent implementation: no source code,
prompts, demo documents, images or model outputs were copied from these tutorials.
The two public brands and their evaluation cases were written for this project.

## Pinned upstream

Repository: [Shubhamsaboo/awesome-llm-apps](https://github.com/Shubhamsaboo/awesome-llm-apps).
Revision: [`4f40918e7f6fb90db5d736f77e91c9a80800dd7e`](https://github.com/Shubhamsaboo/awesome-llm-apps/commit/4f40918e7f6fb90db5d736f77e91c9a80800dd7e),
committed 2026-11-15. This was the default-branch head returned during inspection.
The recursive tree was complete (`truncated: false`). The paths below were verified
against that tree rather than inferred from tutorial names.

| Inspected source | Useful engineering idea | TRACECRAFT implementation and boundary |
| --- | --- | --- |
| [Hybrid search README](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4f40918e7f6fb90db5d736f77e91c9a80800dd7e/rag_tutorials/hybrid_search_rag/README.md), [main.py](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4f40918e7f6fb90db5d736f77e91c9a80800dd7e/rag_tutorials/hybrid_search_rag/main.py) | Separate document processing, retrieval and answer generation; combine lexical and dense retrieval. | ATLAS exposes BM25, dense cosine and reciprocal rank fusion. Missing evidence and unavailable retrieval are explicit. The tutorial's general-knowledge fallback and concealed-context prompt were not adopted. |
| [RAG Failure Diagnostics Clinic README](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4f40918e7f6fb90db5d736f77e91c9a80800dd7e/rag_tutorials/rag_failure_diagnostics_clinic/README.md), [implementation](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4f40918e7f6fb90db5d736f77e91c9a80800dd7e/rag_tutorials/rag_failure_diagnostics_clinic/rag_failure_diagnostics_clinic.py) | A bounded failure vocabulary and a small proposed fix are useful for triage. | LENS reads execution spans. Findings cite recorded events and distinguish observation, hypothesis and reproduction. A pasted narrative or model diagnosis alone does not prove a cause. |
| [Typed Agentic RAG README](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4f40918e7f6fb90db5d736f77e91c9a80800dd7e/rag_tutorials/agentic_typed_rag_pydanticai/README.md), [agent.py](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4f40918e7f6fb90db5d736f77e91c9a80800dd7e/rag_tutorials/agentic_typed_rag_pydanticai/agent.py), [rag.py](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4f40918e7f6fb90db5d736f77e91c9a80800dd7e/rag_tutorials/agentic_typed_rag_pydanticai/rag.py), [tests](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4f40918e7f6fb90db5d736f77e91c9a80800dd7e/rag_tutorials/agentic_typed_rag_pydanticai/test_typed_rag.py) | Typed retrieval tools, output schemas, citation checks and deterministic tests with model requests disabled. | Shared Pydantic contracts separate parsing, admissible values, scope, execution and postconditions. RELAY fixture/local execution is explicitly a workflow. Hashing vectors are not used as a substitute for actual semantic embeddings. |

## Findings that informed the design

The hybrid tutorial catches search errors and returns an empty list; empty retrieval
then enters a general-knowledge fallback. TRACECRAFT preserves the difference between
an unavailable component and an answer absent from accessible documents. Its evidence
is visible. The tutorial reranks a preliminary result, then invokes a separate RAG
call with `search=hybrid_search`; the previously reranked list is not explicitly
passed to that generation call. TRACECRAFT reports the actual context used.

The diagnostics tutorial asks a generative model to classify an incident description.
It checks for empty/truncated output and a required Markdown section before saving a
report. It does not reproduce the failure. LENS therefore uses actual event data and
keeps a regression draft separate from approved expected behavior.

The typed tutorial checks that source quotations exist. That is useful, but source
existence and claim support remain separate questions. Its local hashing backend is
described as keyword-oriented in its README. TRACECRAFT requires an explicitly prepared
real multilingual model for dense retrieval; fixture results are identified as such.

## License inspection

The repository root [LICENSE](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4f40918e7f6fb90db5d736f77e91c9a80800dd7e/LICENSE)
is Apache License 2.0, blob SHA `261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64`.
No separate LICENSE or NOTICE was present in the three selected tutorial directories
or their `rag_tutorials` ancestor. The typed tutorial README explicitly declares
Apache-2.0. The root license contains an unfilled template copyright line; this
project does not invent a copyright holder.

This is a provenance record, not a claim that upstream examples or their dependencies
were executed or independently audited. API examples in those files were not treated
as current official library documentation. Dependency and model licenses remain
separate from the tutorial repository's license.

## Other supplied sources

The three user-supplied Russian notes informed the engineering decisions documented
in [source-to-design.md](source-to-design.md). The original book was not read as part
of this task. The first note is a thematic book summary; the second and third include
explicitly identified interpretations and a proposed practical project. Full notes
and corporate source documents are excluded from the public project.

Akella's allowed source files were inspected read-only for import compatibility.
The importer is independently implemented against the observed catalog contract;
its presence does not grant public redistribution rights to brand data.
