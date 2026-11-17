"""Scoped BM25, real optional dense retrieval and rank fusion; extractive answers."""
import json
import math
import re
import sqlite3
import time
from typing import Literal

from tracecraft.core.embeddings import Encoder, ModelUnavailable, cosine
from tracecraft.core.models import Answer, Claim, EvidenceChunk, RetrievalHit, RetrievalResult, Scope
from tracecraft.core.store import ROOT, Store, digest
from .text import tokens

def reciprocal_rank_fusion(lists, k=60):
    scores: dict[str,float] = {}
    ranks: dict[str,dict[str,int]] = {}
    for name, ordered in lists.items():
        for rank, key in enumerate(ordered, 1):
            scores[key] = scores.get(key, 0) + 1 / (k + rank)
            ranks.setdefault(key, {})[name] = rank
    return sorted(scores, key=lambda key: (-scores[key], key)), scores, ranks

class Atlas:
    answer_policy = 'source-anchor-v3'

    def __init__(self, store: Store, corpus_path=None, encoder=None):
        self.store = store
        self.corpus_path = corpus_path or ROOT / 'datasets/public-demo/corpus.json'
        self.encoder = encoder or Encoder()
        self.chunks = [EvidenceChunk.model_validate(c) for c in json.loads(self.corpus_path.read_text())]
        if len({c.id for c in self.chunks}) != len(self.chunks):
            raise ValueError('Duplicate evidence IDs')
        self.corpus_hash = digest([c.model_dump() for c in self.chunks])

    def eligible(self, scope: Scope):
        return [c for c in self.chunks if c.tenant == scope.tenant and c.brand == scope.brand
                and c.snapshot == scope.snapshot and set(c.permissions) <= set(scope.permissions)
                and c.status == 'reviewed']

    def evidence(self, scope: Scope, id: str):
        return next((c for c in self.eligible(scope) if c.id == id), None)

    def _lexical(self, query, chunks):
        terms = list(dict.fromkeys(tokens(query)))[:48]
        if not terms or not chunks:
            return [], {}, {}
        # Index only scoped records BEFORE BM25, preventing unauthorized corpus statistics leakage.
        # SQLite BM25 is lower-is-better. Never add this score to cosine.
        with sqlite3.connect(':memory:') as db:
            db.execute('CREATE VIRTUAL TABLE search USING fts5(id UNINDEXED,body,tokenize="unicode61")')
            db.executemany('INSERT INTO search VALUES(?,?)', [(c.id, ' '.join(tokens(c.title + ' ' + c.text + ' ' + ' '.join(c.tags)))) for c in chunks])
            expression = ' OR '.join('"' + term.replace('"', '""') + '"' for term in terms)
            rows = db.execute('SELECT id,bm25(search) score FROM search WHERE search MATCH ? ORDER BY score ASC,id', (expression,)).fetchall()
        return [r[0] for r in rows], dict(rows), {}

    def _dense(self, query, chunks):
        vectors = {}
        missing = []
        for c in chunks:
            key = digest([self.encoder.model_id, self.encoder.fingerprint, c.model_dump()])
            stored = self.store.get('embeddings', key)
            if stored:
                vectors[c.id] = stored['vector']
            else:
                missing.append((key, c))
        for offset in range(0, len(missing), 8):
            batch = missing[offset:offset + 8]
            encoded = self.encoder.encode([c.title + '\n' + c.text for _, c in batch], kind='passage')
            for (key, c), vector in zip(batch, encoded):
                self.store.put('embeddings', key, {'vector': vector, 'model': self.encoder.model_id,
                                                  'encoder_fingerprint':self.encoder.fingerprint,
                                                  'source_hash': c.source_hash, 'evidence_id': c.id})
                vectors[c.id] = vector
        q = self.encoder.encode([query], kind='query')[0]
        scores = {c.id: cosine(q, vectors[c.id]) for c in chunks}
        return sorted(scores, key=lambda key: (-scores[key], key)), scores, {}

    def search(self, query: str, scope: Scope, method='lexical', mode='fixture', k=5):
        if not isinstance(query, str) or not query.strip() or len(query) > 2000:
            raise ValueError('Query must contain 1–2000 characters')
        if method not in ('lexical', 'dense', 'hybrid', 'full_pack') or not 1 <= k <= 50:
            raise ValueError('Invalid retrieval configuration')
        if mode not in ('fixture', 'local'):
            return RetrievalResult(query=query, method=method, mode=mode, status='NOT_RUN', reason='Use explicit live provider or recorded replay')
        started = time.perf_counter()
        chunks = self.eligible(scope)
        required = [c for c in chunks if c.mandatory and c.authority == 'explicit' and c.polarity != 'negative']
        if method in ('dense', 'hybrid') and mode == 'fixture':
            return RetrievalResult(query=query, method=method, mode=mode, status='MODEL_NOT_PREPARED',
                                   reason='Fixture profile has no semantic encoder; use prepared local profile.', required=required)
        try:
            if method == 'lexical':
                order, scores, ranks = self._lexical(query, chunks)
            elif method == 'dense':
                order, scores, ranks = self._dense(query, chunks)
            elif method == 'hybrid':
                lexical, _, _ = self._lexical(query, chunks)
                dense, _, _ = self._dense(query, chunks)
                order, scores, ranks = reciprocal_rank_fusion({'lexical': lexical, 'dense': dense})
            else:
                if sum(len(c.text) for c in chunks) > 24000:
                    return RetrievalResult(query=query, method=method, mode=mode, status='NOT_APPLICABLE', reason='Full pack exceeds declared 24,000 character budget')
                order, scores, ranks = [c.id for c in chunks], {c.id: 1.0 for c in chunks}, {}
                k = len(order)
        except (ModelUnavailable, ImportError) as error:
            return RetrievalResult(query=query, method=method, mode=mode, status='MODEL_NOT_PREPARED', reason=str(error))
        by_id = {c.id: c for c in chunks}
        hits = [RetrievalHit(evidence=by_id[key], score=scores[key], rank=i+1, ranks=ranks.get(key, {})) for i, key in enumerate(order[:k])]
        context = {h.evidence.id: h.evidence for h in hits}
        # Preserve links (exception/rule) within exactly the same authorized snapshot.
        for c in list(context.values()) + required:
            context[c.id] = c
            for link in c.links:
                if link in by_id:
                    context[link] = by_id[link]
        return RetrievalResult(query=query, method=method, mode=mode, hits=hits, required=required,
                               context=list(context.values()), latency_ms=(time.perf_counter()-started)*1000,
                               embedding_model=self.encoder.model_id if method in ('dense','hybrid') else None)

    def answer(self, query, scope, method='lexical', mode='fixture', fault=None):
        start = time.perf_counter()
        manifest = self.store.new_run('atlas', mode, {'query': query, 'scope': scope.model_dump(), 'method': method,
                                                   'corpus_hash': self.corpus_hash, 'rrf_k': 60, 'fault': fault,
                                                   'answer_policy':self.answer_policy})
        run_id = manifest['id']
        retrieval = self.search(query, scope, method, mode)
        self.store.trace(run_id, 'retrieval', {'query': query, 'scope': scope.model_dump(), 'method': method},
                         {'status': retrieval.status, 'retrieved_ids': [h.evidence.id for h in retrieval.hits],
                          'scores': [h.score for h in retrieval.hits], 'context_ids': [c.id for c in retrieval.context],
                          'context': [c.model_dump() for c in retrieval.context]})
        context = retrieval.context
        if fault == 'omit_evidence':
            context = []
            self.store.trace(run_id, 'context', {'injected_fault': fault}, {'context_ids': []}, status='error', error='Evidence intentionally omitted in isolated demo')
        elif fault is not None:
            raise ValueError('Unknown isolated fault')
        q_terms = set(tokens(query))
        # Source headings/tags anchor the requested subject. A distinctive body
        # term also permits an exact name/quotation lookup. A whole-query coverage
        # cutoff would penalize polite wording and legitimate multi-part questions.
        vocabulary = {c.id:set(tokens(c.title + ' ' + c.text + ' ' + ' '.join(c.tags)))
                      for c in self.eligible(scope)}
        weights = {term:math.log(1 + (len(vocabulary)+1)/(1+sum(term in v for v in vocabulary.values())))
                   for term in q_terms}
        total = sum(weights.values()) or 1
        scores = {c.id:sum(weights[t] for t in q_terms & vocabulary.get(c.id,set()))/total for c in context}
        # These describe the surrounding task, not a rule attribute. In particular
        # a return-period question mentioning a product must not answer photography.
        context_terms=set(tokens('product продукт banner баннер digital цифровой launch стартовый approved'))
        subjects=q_terms-context_terms
        rare = {term for term in subjects if sum(term in v for v in vocabulary.values())==1}
        relevant = [c for c in context if subjects & set(tokens(c.title+' '+' '.join(c.tags)))
                    or rare & vocabulary.get(c.id,set())]
        # Color-space conversions are distinct requested attributes, not a license
        # to present a named/hex color as the missing conversion. This is a declared
        # domain intent guard, not invented brand data or a universal intent model.
        formats = re.findall(r'\b(?:cmyk|pantone|rgb|hsl|hsv|ral)\b',query.casefold())
        if formats and not all(any(fmt in (c.title+' '+c.text).casefold() for c in relevant) for fmt in formats):
            relevant = []
        action_requested=bool(re.search(r'\b(?:publish|send|execute|delete|remove|upload|опубликуй\w*|отправь\w*|удали\w*|выполни\w*)\b',query.casefold()))
        self.store.trace(run_id,'evidence_selection',{'query_terms':sorted(q_terms),'policy':self.answer_policy},
                         {'coverage':scores,'selected_ids':[c.id for c in relevant]})
        # Include linked exceptions and conflicting peer rules even if words differ.
        relevant_ids = {c.id for c in relevant}
        keys = {c.rule_key for c in relevant if c.rule_key}
        links = {link for c in relevant for link in c.links}
        relevant += [c for c in context if c.id not in relevant_ids and (c.id in links or c.rule_key and c.rule_key in keys)]
        rules = [c for c in relevant if c.authority == 'explicit' and c.kind != 'example' and c.polarity != 'negative']
        values: dict[str,set[str]] = {}
        for c in rules:
            if c.rule_key:
                values.setdefault(c.rule_key, set()).add(c.value)
        conflict = any(len(v) > 1 for v in values.values())
        status: Literal['supported','insufficient_evidence','conflict','needs_review']
        if retrieval.status != 'ready':
            status, text = 'needs_review', retrieval.reason or retrieval.status
            rules = []
        elif action_requested:
            status,text='needs_review','This read-only answer cannot authorize or execute an action; use the reviewed workflow.'
            rules=[]
        elif conflict:
            status, text = 'conflict', 'Sources conflict; a reviewed priority decision is required.\n' + '\n'.join(c.text for c in rules)
        elif rules:
            status, text = 'supported', '\n\n'.join(c.text for c in rules)
        elif any(q_terms & set(tokens(c.title+' '+' '.join(c.tags))) for c in relevant):
            status, text = 'needs_review', 'Only observations or examples found; these do not establish an authoritative rule.'
        else:
            status, text = 'insufficient_evidence', 'No applicable rule found in the permitted snapshot.'
        answer = Answer(status=status, text=text, evidence_ids=[c.id for c in rules],
                        claims=[Claim(text=c.text, evidence_id=c.id, quote=c.text) for c in rules],
                        retrieval=retrieval, mode=mode, latency_ms=(time.perf_counter()-start)*1000,
                        generation_kind='deterministic_extractive' if mode == 'fixture' else 'local_extractive', run_id=run_id)
        self.store.trace(run_id, 'answer_validation', {'evidence_ids': answer.evidence_ids},
                         {'status': status, 'claims': [c.model_dump() for c in answer.claims], 'generation_kind': answer.generation_kind})
        self.store.put('answers', run_id, answer.model_dump())
        self.store.finish_run(run_id, 'succeeded', answer_status=status, latency_ms=answer.latency_ms)
        return answer

def experiment(store, atlas, mode='fixture'):
    from tracecraft.canon import run_benchmark
    results = {method: run_benchmark(store, atlas, mode=mode, method=method) for method in ('lexical','dense','hybrid')}
    return {'module': 'atlas', 'mode': mode, 'data_origin': 'synthetic', 'measurement_status': 'measured',
            'methods': results, 'limitations': ['Exploratory synthetic corpus; extractive output, no LLM quality inference.',
                                              'Scores measure retrieval affinity, not truth probability.']}
