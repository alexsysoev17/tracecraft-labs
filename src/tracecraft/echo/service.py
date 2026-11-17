"""Conservative answer cache: proximity proposes; compatibility decides."""
import json
import re
import threading
import time
import uuid

from tracecraft.core.embeddings import ModelUnavailable, cosine
from tracecraft.core.models import Answer, CacheEntry, Scope
from tracecraft.core.store import ROOT, digest

LOCKS = [threading.Lock() for _ in range(64)]
OBJECTS = {
    'palette': r'color|colour|palette|hex|цвет|палитр|оттен',
    'clearspace': r'clearspace|clearance|spacing|space|охранн|отступ|расстояни',
    'logo': r'logo|wordmark|логотип|знак',
    'font': r'font|typeface|typography|шрифт|типограф',
    'discount': r'discount|скидк|sale',
    'packaging': r'packag|упаков',
    'name': r'name|назван',
}
NEGATION = r'\b(?:not|no|never|without|except|не|нет|нельзя|без|кроме)\b'
UNSAFE = r'new variant|another variant|новый вариант|ещ[её] вариант|approve|approval|согласу|publish|публику|send|отправ|today|сегодня|my current|мой текущ|уточн|\bdelete\b|\bremove\b|\bupdate\b|\bexecute\b|\bchange\b|\breplace\b|\bcreate\b|удали|удалить|измени|замени|создай|выполни|обнови'

def normalize(query):
    # Exact cache is deliberately conservative: punctuation can change numbers/codes.
    return ' '.join(query.casefold().split())

def signature(query):
    q = query.casefold()
    objects = sorted(name for name, pattern in OBJECTS.items() if re.search(pattern, q))
    # Numbers, dates, exact codes and negation survive a near-identical embedding.
    numbers = re.findall(r'\d+(?:[.,]\d+)?%?', q)
    codes = re.findall(r'\b[a-z]{2,}(?:-[a-z0-9]+)+\b|#[a-f0-9]{3,8}', q)
    # Additional operation/context changes may not reuse a ready answer.
    modifiers = re.findall(r'rotate|stretch|print|digital|mobile|banner|poster|повер\w*|растян\w*|печат\w*|цифров\w*|мобиль\w*|баннер\w*|плакат\w*', q)
    noise = set('what is are the a an of for in and to can how which use used should please tell me about primary main show describe какой какая какие как и в на для ли что можно нужно основной основная расскажи покажи используется'.split())
    residual = sorted(t for t in re.findall(r'\w+',q) if t not in noise and not any(re.search(p,t) for p in OBJECTS.values()))
    return {'objects': objects, 'numbers': numbers, 'codes': codes, 'negative': bool(re.search(NEGATION, q)), 'modifiers': modifiers, 'residual':residual}

def compatible_query(a, b):
    sa, sb = signature(a), signature(b)
    return bool(sa['objects']) and sa == sb and not re.search(UNSAFE, a.casefold() + ' ' + b.casefold())

class Echo:
    def __init__(self, store, atlas, ttl=3600, max_entries=128):
        self.store, self.atlas = store, atlas
        self.ttl, self.max_entries = ttl, max_entries

    def namespace(self, scope, mode, method):
        return digest({'scope': scope.model_dump(), 'corpus': self.atlas.corpus_hash, 'mode': mode,
                       'retrieval': method, 'prompt':self.atlas.answer_policy, 'generation':self.atlas.answer_policy,
                       'tools': 'read-only-v1', 'embedding': self.atlas.encoder.model_id,
                       'encoder_config':self.atlas.encoder.fingerprint})

    def calibration_key(self):
        return digest([self.atlas.encoder.model_id,self.atlas.encoder.fingerprint])

    def cleanup(self):
        entries = self.store.list('cache')
        for item in entries:
            if item['expires_at'] <= time.time():
                self.store.delete('cache', item['id'])
        remaining = sorted(self.store.list('cache'), key=lambda item: item['created_at'])
        for item in remaining[:max(0, len(remaining)-self.max_entries)]:
            self.store.delete('cache', item['id'])

    def valid(self, entry, scope):
        answer = entry['answer']
        if answer['status'] != 'supported' or not answer['evidence_ids'] or not answer['claims'] or entry['expires_at'] <= time.time():
            return False
        if answer['text'] != '\n\n'.join(c['text'] for c in answer['claims']):
            return False
        for key, source_hash in entry['dependencies'].items():
            evidence = self.atlas.evidence(scope, key)
            if not evidence or evidence.source_hash != source_hash:
                return False
        for claim in answer['claims']:
            evidence = self.atlas.evidence(scope, claim['evidence_id'])
            if not evidence or claim['quote'] not in evidence.text or claim['text'] != claim['quote']:
                return False
        if {c['evidence_id'] for c in answer['claims']} != set(answer['evidence_ids']):
            return False
        # A cache response includes the retrieval inspector, not only cited claims.
        # Revalidate every returned source so revoked uncited context cannot leak.
        retrieval = answer.get('retrieval') or {}
        returned = retrieval.get('context',[]) + retrieval.get('required',[]) + [h['evidence'] for h in retrieval.get('hits',[])]
        for saved in returned:
            current = self.atlas.evidence(scope,saved['id'])
            if not current or current.model_dump() != saved:
                return False
        return set(answer['evidence_ids']) == set(entry['dependencies'])

    def invalidate(self, scope):
        # Conservative invalidation, current corpus namespace only. No TTL-only freshness claim.
        count = 0
        namespaces = {self.namespace(scope,mode,method) for mode in ('fixture','local')
                      for method in ('lexical','dense','hybrid','full_pack')}
        for entry in self.store.list('cache'):
            if entry['namespace'] in namespaces and not self.valid(entry, scope):
                self.store.delete('cache', entry['id'])
                count += 1
        return count

    def request(self, query, scope=None, policy='semantic', mode='fixture', method='lexical'):
        scope = scope or Scope()
        if policy not in ('off', 'exact', 'semantic'):
            raise ValueError('Invalid cache policy')
        if mode not in ('fixture','local'):
            return {'status': 'NOT_RUN', 'mode': mode, 'reason': 'Use recorded replay or opt-in live runner'}
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 2000:
            raise ValueError('Invalid cache query')
        start = time.perf_counter()
        namespace = self.namespace(scope, mode, method)
        key = digest([namespace, normalize(query)])
        # Bounded lock stripes provide single-flight for identical calls in the single server process.
        with LOCKS[int(key[:8], 16) % len(LOCKS)]:
            self.cleanup()
            entries = [e for e in self.store.list('cache') if e['namespace'] == namespace]
            reason = 'cache_off' if policy == 'off' else 'no_compatible_entry'
            hit = None
            score = None
            vector = None
            lookup_started = time.perf_counter()
            embedding_before = self.atlas.encoder.calls
            unsafe = bool(re.search(UNSAFE, query.casefold()))
            if unsafe:
                reason = 'read_only_policy_rejected'
            if policy != 'off' and not unsafe:
                hit = next((e for e in entries if normalize(e['query']) == normalize(query) and self.valid(e, scope)), None)
                if hit:
                    reason = 'exact_match'
                elif policy == 'semantic':
                    calibration = self.store.get('cache_config', self.calibration_key())
                    if mode == 'fixture':
                        reason = 'semantic_unavailable_in_fixture'
                    elif not calibration:
                        reason = 'threshold_not_calibrated'
                    else:
                        try:
                            vector = self.atlas.encoder.encode([query])[0]
                            candidates = sorted([(cosine(vector, e['vector']), e) for e in entries if e['vector']], key=lambda x: -x[0])
                            for similarity, entry in candidates:
                                if similarity < calibration['threshold']:
                                    reason = 'below_validation_threshold'
                                    continue
                                if not compatible_query(entry['query'], query):
                                    reason = 'semantic_guard_rejected'
                                    continue
                                if not self.valid(entry, scope):
                                    reason = 'provenance_or_access_changed'
                                    continue
                                hit, score, reason = entry, similarity, 'semantic_verified'
                                break
                        except (ModelUnavailable, ImportError) as error:
                            reason = 'model_unavailable: ' + str(error)
            lookup_ms = (time.perf_counter()-lookup_started)*1000
            if hit:
                answer = Answer.model_validate(hit['answer'])
                actual_calls = 0
                admitted = False
            else:
                answer = self.atlas.answer(query, scope, method=method, mode=mode)
                actual_calls = 1
                dependencies = {id: self.atlas.evidence(scope, id).source_hash for id in answer.evidence_ids if self.atlas.evidence(scope, id)}
                admitted = policy != 'off' and not unsafe and answer.status == 'supported' and bool(dependencies)
                if admitted:
                    if mode == 'local' and policy == 'semantic' and vector is None:
                        try:
                            vector = self.atlas.encoder.encode([query])[0]
                        except (ModelUnavailable, ImportError):
                            vector = None
                    entry = CacheEntry(id=key, query=query, namespace=namespace, created_at=time.time(),
                                       expires_at=time.time()+self.ttl, answer=answer, dependencies=dependencies,
                                       vector=vector, embedding_model=self.atlas.encoder.model_id if vector else None).model_dump()
                    if self.valid(entry, scope):
                        self.store.put('cache', key, entry)
                        self.cleanup()
                    else:
                        admitted = False
            latency = (time.perf_counter()-start)*1000
            run = self.store.new_run('echo', mode, {'policy': policy, 'query': query, 'scope': scope.model_dump(), 'namespace': namespace})
            result = {'run_id': run['id'], 'status': 'ready', 'mode': mode, 'policy': policy, 'hit': bool(hit),
                      'hit_type': reason if hit else None, 'reason': reason, 'similarity': score, 'admitted': admitted,
                      'answer': answer.model_dump(), 'answer_calls': actual_calls, 'llm_calls': 0,
                      'embedding_calls': self.atlas.encoder.calls - embedding_before, 'lookup_verification_ms': lookup_ms,
                      'latency_ms': latency, 'cost_usd': None, 'data_origin': 'synthetic', 'measurement_status': 'measured'}
            self.store.trace(run['id'], 'cache_decision', {'query': query, 'namespace': namespace}, result)
            self.store.finish_run(run['id'], 'succeeded', latency_ms=latency)
            return result

    def calibrate(self):
        pairs = json.loads((ROOT / 'datasets/public-demo/cache-validation.json').read_text())
        observations = []
        for pair in pairs:
            a, b = self.atlas.encoder.encode([pair['a'], pair['b']])
            observations.append({**pair, 'similarity': cosine(a,b), 'guard': compatible_query(pair['a'],pair['b'])})
        thresholds = sorted({0.80, 0.85, 0.90, 0.95, 0.98} | {o['similarity'] for o in observations})
        choices = []
        for threshold in thresholds:
            accepted = [o for o in observations if o['similarity'] >= threshold and o['guard']]
            fp = sum(not o['safe'] for o in accepted)
            tp = sum(o['safe'] for o in accepted)
            choices.append((fp, -tp, -threshold, threshold))
        threshold = min(choices)[3]
        result = {'threshold': threshold, 'split': 'validation', 'dataset_hash': digest(pairs),
                  'model': self.atlas.encoder.model_id, 'observations': observations,
                  'limitations': 'Small authored validation set; no universal threshold or safety guarantee.'}
        result['encoder_fingerprint'] = self.atlas.encoder.fingerprint
        self.store.put('cache_config', self.calibration_key(), result)
        return result

def experiment(store, atlas, mode='fixture'):
    calibration = None
    if mode == 'local':
        try:
            calibration = Echo(store, atlas).calibrate()
        except (ModelUnavailable, ImportError) as error:
            calibration = {'status': 'MODEL_NOT_PREPARED', 'reason': str(error)}
    cases = [
        ('first', 'What is the primary color?', Scope()),
        ('repeat', 'What is the primary color?', Scope()),
        ('paraphrase', 'Tell me the primary colour.', Scope()),
        ('other_brand', 'What is the primary color?', Scope(brand='veyra')),
        ('other_version', 'What is the primary color?', Scope(snapshot='v1')),
        ('number', 'What is the primary color for 20 banners?', Scope()),
        ('negation', 'What is not the primary color?', Scope()),
        ('clarification', 'Уточнение: What is the primary color?', Scope(context='Print only')),
        ('revoked_access', 'What is the primary color?', Scope(permissions=[], acl_version='2')),
    ]
    policies = {}
    for policy in ('off','exact','semantic'):
        # A fresh persisted namespace per policy ensures a real matched no-cache control.
        cache = Echo(store, atlas)
        nonce = uuid.uuid4().hex
        rows = []
        for name, query, scope in cases:
            scope = scope.model_copy(update={'project': 'echo-experiment-' + nonce})
            result = cache.request(query, scope, policy=policy, mode=mode)
            result['case'] = name
            result['expected_miss'] = name not in ('repeat','paraphrase')
            rows.append(result)
        unsafe = [r for r in rows if r['expected_miss'] and r['hit']]
        policies[policy] = {'requests': len(rows), 'hits': sum(r['hit'] for r in rows),
                            'false_hits': len(unsafe), 'false_hit_rate': len(unsafe)/len(rows),
                            'answer_calls': sum(r['answer_calls'] for r in rows), 'llm_calls': 0,
                            'latency_ms': sum(r['latency_ms'] for r in rows), 'cost_usd': None, 'rows': rows}
    return {'module': 'echo', 'mode': mode, 'data_origin': 'synthetic', 'measurement_status': 'measured',
            'calibration': calibration, 'policies': policies,
            'limitations': ['Measured downstream extractive calls, not LLM savings. CPU time and order affect tiny samples.',
                           'Answer cache only; provider prompt cache and embedding cache are separate.',
                           'Fixture semantic reuse is unavailable; exact hits remain real.']}
