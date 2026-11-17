"""RELAY is an explicit workflow in fixture/local mode, not autonomous planning.

Only SQLite artifact writes are effects. Artifact content, idempotency ledger and
checkpoint commit together. Filesystem export is a repeatable projection of those
records; no external action is replayed.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tracecraft.core.models import Artifact, Scope, ToolCall, TraceSpan
from tracecraft.core.store import Store, canonical, digest, utcnow


class RelayError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class Brief(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    brand: Literal['luma', 'veyra'] = 'luma'
    objective: str | None = Field(default=None, max_length=1200)
    width: int | None = Field(default=None, ge=64, le=8192)
    height: int | None = Field(default=None, ge=64, le=8192)
    copy_text: str | None = Field(default=None, alias='copy', max_length=2000)


class SearchArgs(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    query: str = Field(min_length=1, max_length=2000)


class EvidenceArgs(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    evidence_id: str = Field(min_length=1, max_length=200)


class NoArgs(BaseModel):
    model_config = ConfigDict(extra='forbid')


class QuestionsArgs(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    fields: list[str] = Field(min_length=1, max_length=4)


ARG_MODELS: dict[str, type[BaseModel]] = {
    'search_rules': SearchArgs,
    'read_evidence': EvidenceArgs,
    'validate_requirements': NoArgs,
    'request_clarification': QuestionsArgs,
    'draft_handoff': NoArgs,
    'request_review': NoArgs,
}
REQUIRED = ('objective', 'width', 'height', 'copy')
QUESTIONS = {
    'objective': 'Какова цель баннера?',
    'width': 'Какова ширина в пикселях?',
    'height': 'Какова высота в пикселях?',
    'copy': 'Какой точный текст нужно использовать?',
}
TERMINAL = {'succeeded', 'cancelled'}


def _get(db, namespace: str, key: str):
    row = db.execute('SELECT value FROM records WHERE namespace=? AND key=?', (namespace, key)).fetchone()
    return json.loads(row[0]) if row else None


def _put(db, namespace: str, key: str, value: Any):
    db.execute('INSERT OR REPLACE INTO records VALUES(?,?,?,?)', (namespace, key, canonical(value), time.time()))


def _span(db, run_id: str, stage: str, inputs: dict, outputs: dict,
          status: str = 'ok', error: str | None = None):
    span = TraceSpan(id=uuid.uuid4().hex, run_id=run_id, timestamp=utcnow(), stage=stage,
                     inputs=inputs, outputs=outputs, status=status, error=error).model_dump()
    _put(db, 'spans', span['id'], span)
    return span


def _manifest(db, run_id: str, state: str):
    run = _get(db, 'runs', run_id)
    run.update(status=state, measurement_status='measured')
    if state in TERMINAL or state == 'failed':
        run['finished_at'] = utcnow()
    _put(db, 'runs', run_id, run)


def _scope_equal(a: Scope, b: Scope):
    return a.model_dump() == b.model_dump()


class Relay:
    def __init__(self, store: Store, atlas):
        self.store = store
        self.atlas = atlas

    def _authorize(self, state: dict, scope: Scope | None):
        saved = Scope.model_validate(state['scope'])
        principal = scope or Scope(brand=saved.brand, snapshot=saved.snapshot)
        if not _scope_equal(saved, principal):
            raise RelayError('permission', 'Run is outside the current demo scope.')
        return saved

    def get(self, run_id: str, scope: Scope | None = None) -> dict:
        state = self.store.get('relay', run_id)
        if state is None:
            raise KeyError(run_id)
        self._authorize(state, scope)
        return state

    def create(self, brief: dict, mode: str = 'fixture', scope: Scope | None = None,
               deadline_seconds: float = 300) -> dict:
        if mode not in {'fixture', 'local'}:
            raise RelayError('MODE_NOT_AVAILABLE', 'RELAY live planning is not configured; recorded replay belongs to LENS.')
        state = self._initialize(brief, mode, scope, deadline_seconds)
        return self.resume(state['id'], scope=scope)

    def _initialize(self, brief: dict, mode: str, scope: Scope | None, deadline_seconds: float) -> dict:
        if not 0 < deadline_seconds <= 3600:
            raise RelayError('invalid_args', 'Deadline must be between 0 and 3600 seconds.')
        parsed = Brief.model_validate(brief).model_dump(by_alias=True)
        scope = scope or Scope(brand=parsed['brand'])
        if scope.brand != parsed['brand']:
            raise RelayError('permission', 'Brief brand and authorized scope differ.')
        config = {'workflow': 'banner-handoff/1', 'scope': scope.model_dump(), 'max_retries': 1,
                  'deadline_seconds': deadline_seconds, 'tool_version': 'relay-tools/1'}
        run = self.store.new_run('relay', mode, config)
        state = {'id': run['id'], 'state': 'queued', 'mode': mode,
                 'workflow_kind': ('model_tool_proposals_with_deterministic_handoff' if mode == 'live'
                                   else 'deterministic_workflow'), 'data_origin': 'synthetic',
                 'brief': parsed, 'scope': scope.model_dump(), 'input_hash': digest({'brief': parsed, 'scope': scope.model_dump()}),
                 'artifact_hash': None, 'artifact_ids': [], 'evidence_ids': [], 'dependencies': {},
                 'questions': [], 'revision': 0, 'attempts': 0, 'deadline_at': time.time() + deadline_seconds,
                 'created_at': utcnow(), 'updated_at': utcnow(), 'approval': None, 'error': None}
        if mode == 'live':
            # The immutable session identifies usage; the owner is revoked by cancellation.
            state['live_session'] = uuid.uuid4().hex
            state['live_owner'] = state['live_session']
        self.store.put('relay', run['id'], state)
        return state

    def _claim(self, run_id: str, answers: dict | None, scope: Scope | None):
        with self.store.transaction() as db:
            state = _get(db, 'relay', run_id)
            if state is None:
                raise KeyError(run_id)
            self._authorize(state, scope)
            revised = None
            if answers:
                if set(answers) - set(REQUIRED):
                    raise RelayError('invalid_args', 'Only requested brief fields may be changed; scope cannot be changed.')
                revised = Brief.model_validate({**state['brief'], **answers}).model_dump(by_alias=True)
            changed = revised is not None and revised != state['brief']
            if state['state'] in TERMINAL:
                if changed:
                    raise RelayError('terminal_run', 'Create a new run to change a completed or cancelled task.')
                return state, None
            if state['state'] == 'running' and state.get('lease_until', 0) > time.time():
                # An active owner computes read-only steps. Committed effects remain unique.
                active_owner = False
                try:
                    owner_pid = state.get('owner_pid', 0)
                    if isinstance(owner_pid, int) and owner_pid > 0:
                        os.kill(owner_pid, 0)
                        active_owner = True
                except PermissionError:
                    active_owner = True
                except OSError:
                    pass
                if active_owner:
                    if changed:
                        raise RelayError('conflicting_resume', 'Another worker is preparing this brief; retry the changed input after it pauses.')
                    # Same-input retries observe the current operation without duplicating it.
                    return state, None
            if changed:
                state['brief'] = revised
                state['input_hash'] = digest({'brief': revised, 'scope': state['scope']})
                state['approval'] = None
                state['artifact_hash'] = None
                state['artifact_ids'] = []
            elif state['state'] == 'awaiting_approval':
                return state, None
            if time.time() > state['deadline_at']:
                state.update(state='failed', error={'code': 'timeout', 'message': 'Workflow deadline exceeded.'})
                _span(db, run_id, 'deadline', {'deadline_at': state['deadline_at']}, {}, 'error', 'timeout')
                _put(db, 'relay', run_id, state)
                _manifest(db, run_id, 'failed')
                return state, None
            token = uuid.uuid4().hex
            state.update(state='running', operation_token=token, owner_pid=os.getpid(), lease_until=time.time() + 30,
                         revision=state['revision'] + 1, updated_at=utcnow(), error=None)
            _put(db, 'relay', run_id, state)
            _manifest(db, run_id, 'running')
            return state, token

    def _record_tool(self, state: dict, name: str, args: dict, outputs: dict, proposal_kind: str = 'workflow'):
        self.store.trace(state['id'], 'tool.proposed', {'name': name, 'arguments': args,
                         'proposal_kind': proposal_kind},
                         {'schema': 'valid', 'values': 'valid', 'scope': 'allowed'})
        self.store.trace(state['id'], 'tool.executed', {'name': name, 'arguments': args}, outputs)

    def execute_tool(self, run_id: str, payload: dict | str, scope: Scope | None = None) -> dict:
        """Validate an explicit proposal; fixture callers cannot execute arbitrary code.

        Draft/review tools request persisted workflow transitions. No tool selects
        paths, publishes content, changes credentials or changes an approval.
        """
        state = self.get(run_id, scope)
        try:
            call = ToolCall.model_validate_json(payload) if isinstance(payload, str) else ToolCall.model_validate(payload)
            if not 1 <= len(call.idempotency_key) <= 200:
                raise ValueError('Invalid idempotency key')
            args = ARG_MODELS[call.name].model_validate(call.arguments).model_dump()
        except (ValidationError, ValueError, KeyError) as exc:
            self.store.trace(run_id, 'tool.validation', {'proposal_type': type(payload).__name__},
                             {'executed': False, 'validation': 'schema_or_values'}, 'error', 'invalid_args')
            raise RelayError('invalid_args', 'Tool proposal failed parsing/schema/value validation.') from exc
        if state['state'] in TERMINAL:
            raise RelayError('terminal_run', 'Terminal tasks cannot execute new tools.')
        parsed_scope = self._authorize(state, scope)
        if call.name == 'search_rules':
            result = self.atlas.search(args['query'], parsed_scope, method='lexical',
                                       mode='local' if state['mode'] == 'live' else state['mode'])
            output = result.model_dump()
        elif call.name == 'read_evidence':
            item = self.atlas.evidence(parsed_scope, args['evidence_id'])
            if item is None:
                self.store.trace(run_id, 'tool.validation', {'name': call.name}, {'executed': False}, 'error', 'permission')
                raise RelayError('permission', 'Evidence is absent or outside the authorized scope.')
            output = item.model_dump()
        elif call.name == 'validate_requirements':
            output = {'missing': self._missing(state['brief']), 'schema_valid': True}
        elif call.name == 'request_clarification':
            if set(args['fields']) - set(self._missing(state['brief'])):
                raise RelayError('invalid_args', 'Clarification fields must actually be missing from the brief.')
            output = {'questions': [QUESTIONS[field] for field in args['fields']]}
            if state['mode'] == 'live':
                with self.store.transaction() as db:
                    current = _get(db, 'relay', run_id)
                    if current['state'] in TERMINAL:
                        raise RelayError('terminal_run', 'The task ended before clarification could be saved.')
                    if (current.get('live_owner') != state.get('live_owner') or
                            current['revision'] != state['revision'] or current['input_hash'] != state['input_hash']):
                        raise RelayError('conflicting_resume', 'The brief changed before clarification could be saved.')
                    current.update(state='awaiting_input', updated_at=utcnow(),
                                   questions=[{'field': name, 'question': QUESTIONS[name]} for name in args['fields']])
                    _put(db, 'relay', run_id, current)
                    _manifest(db, run_id, 'awaiting_input')
        else:
            if self._missing(state['brief']):
                raise RelayError('invalid_args', 'A handoff or review requires a complete brief.')
            if call.name == 'request_review' and not state['artifact_hash']:
                raise RelayError('postcondition', 'Review requires a persisted and checked artifact package.')
            output = self.resume(run_id, scope=scope)
        self._record_tool(state, call.name, args, output, 'model' if state['mode'] == 'live' else 'explicit_test_proposal')
        return output

    @staticmethod
    def _missing(brief: dict) -> list[str]:
        return [field for field in REQUIRED if brief.get(field) is None or
                (isinstance(brief.get(field), str) and not brief[field].strip())]

    def resume(self, run_id: str, answers: dict | None = None, scope: Scope | None = None) -> dict:
        state, token = self._claim(run_id, answers, scope)
        if token is None:
            return state
        parsed_scope = Scope.model_validate(state['scope'])
        missing = self._missing(state['brief'])
        self._record_tool(state, 'validate_requirements', {}, {'missing': missing, 'schema_valid': True})
        if missing:
            questions = [{'field': name, 'question': QUESTIONS[name]} for name in missing]
            self._record_tool(state, 'request_clarification', {'fields': missing}, {'questions': questions})
            return self._commit_state(state, token, 'awaiting_input', questions=questions)
        try:
            last_error = None
            result = None
            for attempt in range(2):
                state['attempts'] = attempt + 1
                if time.time() > state['deadline_at']:
                    raise RelayError('timeout', 'Workflow deadline exceeded before search.')
                try:
                    result = self.atlas.search(state['brief']['objective'], parsed_scope,
                                               method='lexical', mode='local' if state['mode'] == 'live' else state['mode'], k=6)
                    if result.status != 'ready':
                        raise RelayError('missing_source', result.reason or result.status)
                    self._record_tool(state, 'search_rules', {'query': state['brief']['objective']}, result.model_dump())
                    break
                except (TimeoutError, OSError) as exc:
                    last_error = exc
                    self.store.trace(run_id, 'tool.retry', {'tool': 'search_rules', 'attempt': attempt + 1},
                                     {'retry_allowed': attempt == 0}, 'error', 'tool_execution')
            if result is None:
                raise RelayError('tool_execution', str(last_error))
            by_id = {c.id: c for c in [*result.required, *result.context, *(h.evidence for h in result.hits)]}
            authoritative = [c for c in by_id.values() if c.authority == 'explicit' and c.status == 'reviewed'
                             and c.kind in {'rule', 'editorial'} and c.polarity != 'negative']
            if not authoritative:
                raise RelayError('missing_source', 'No applicable reviewed explicit rules are available.')
            rules = sorted(authoritative, key=lambda c: c.id)
            conflicts: dict[str, set[str]] = {}
            for rule in rules:
                if rule.rule_key:
                    conflicts.setdefault(rule.rule_key, set()).add(rule.value)
            conflicting = [key for key, values in conflicts.items() if len(values) > 1]
            for rule in rules:
                current = self.atlas.evidence(parsed_scope, rule.id)
                if current is None or current.source_hash != rule.source_hash:
                    raise RelayError('stale_source', 'Evidence changed during preparation.')
                self._record_tool(state, 'read_evidence', {'evidence_id': rule.id}, current.model_dump())
            if conflicting:
                self.store.trace(run_id, 'requirements.conflict', {'rule_keys': conflicting},
                                 {'needs_human_resolution': True}, 'error', 'conflict')
                return self._commit_state(state, token, 'awaiting_input', questions=[
                    {'field': 'source_review', 'question': 'Resolve conflicting source rules before continuing: ' + ', '.join(conflicting)}],
                    error={'code': 'conflict', 'message': 'Source conflicts require corpus review, not a guessed priority.'})
            package = self._package(state, rules)
            self._record_tool(state, 'draft_handoff', {}, {'artifact_names': [a['name'] for a in package],
                                                        'postcondition': 'validated'})
            return self._commit_package(state, token, package, rules)
        except (RelayError, ValueError, OSError) as exc:
            code = exc.code if isinstance(exc, RelayError) else 'tool_execution'
            self.store.trace(run_id, 'workflow.failure', {}, {'executed': False}, 'error', code)
            return self._commit_state(state, token, 'failed', error={'code': code, 'message': str(exc)})

    def _commit_state(self, previous: dict, token: str, status: str, **fields) -> dict:
        with self.store.transaction() as db:
            current = _get(db, 'relay', previous['id'])
            if current.get('operation_token') != token or current['state'] == 'cancelled':
                return current
            current.update(state=status, updated_at=utcnow(), lease_until=0, attempts=previous['attempts'], **fields)
            _put(db, 'relay', current['id'], current)
            _manifest(db, current['id'], status)
        return current

    def _package(self, state: dict, rules: list) -> list[dict]:
        requirements = {'schema': 'tracecraft.requirements/1', 'brief': state['brief'],
                        'scope': state['scope'], 'input_hash': state['input_hash'],
                        'rules': [{'evidence_id': r.id, 'text': r.text, 'source_hash': r.source_hash,
                                   'section': r.section} for r in rules], 'unknowns': []}
        handoff = ['# Designer handoff', '', 'This package contains requirements, not rendered banner pixels.', '',
                   f"Brand: {state['brief']['brand']}", f"Objective: {state['brief']['objective']}",
                   f"Format: {state['brief']['width']} × {state['brief']['height']} px", '',
                   '## Exact supplied copy', '', state['brief']['copy'], '', '## Applicable source rules', '']
        handoff += [f'- {r.text} [{r.id}] ({r.section}; SHA256 {r.source_hash})' for r in rules]
        handoff += ['', 'Human review confirms this exact package and the bound input snapshot.']
        contents = {'requirements.json': (json.dumps(requirements, ensure_ascii=False, indent=2), 'application/json'),
                    'questions.md': ('# Questions\n\nNo brief fields are missing. Source rules remain subject to human review.\n', 'text/markdown'),
                    'handoff.md': ('\n'.join(handoff) + '\n', 'text/markdown')}
        package = []
        for name, (content, media) in contents.items():
            aid = f"{state['id']}:{state['input_hash']}:{name}"
            package.append(Artifact(id=aid, run_id=state['id'], name=name, content=content,
                                    sha256=digest(content.encode()), media_type=media).model_dump())
        # Verify objective postconditions, not a model's declaration of success.
        parsed = json.loads(contents['requirements.json'][0])
        if parsed['brief'] != state['brief'] or not parsed['rules'] or state['brief']['copy'] not in contents['handoff.md'][0]:
            raise RelayError('postcondition', 'Handoff content does not satisfy the brief.')
        return package

    def _commit_package(self, previous: dict, token: str, package: list[dict], rules: list) -> dict:
        with self.store.transaction() as db:
            state = _get(db, 'relay', previous['id'])
            if state.get('operation_token') != token or state['state'] == 'cancelled':
                return state
            if time.time() > state['deadline_at']:
                state.update(state='failed', error={'code': 'timeout', 'message': 'Deadline exceeded before commit.'})
                _put(db, 'relay', state['id'], state)
                _manifest(db, state['id'], 'failed')
                return state
            dependencies = {r.id: r.source_hash for r in rules}
            bundle_hash = digest({'artifacts': {a['name']: a['sha256'] for a in package},
                                  'input_hash': state['input_hash'], 'dependencies': dependencies})
            effect_key = f"{state['id']}:{state['input_hash']}:draft_handoff"
            existing = _get(db, 'relay_effects', effect_key)
            if existing and existing['artifact_hash'] != bundle_hash:
                raise RelayError('stale_source', 'Same inputs produced a changed package; start a new run with a new snapshot.')
            for artifact in package:
                _put(db, 'artifacts', artifact['id'], artifact)
            _put(db, 'relay_effects', effect_key, {'id': effect_key, 'run_id': state['id'],
                                                'artifact_hash': bundle_hash, 'input_hash': state['input_hash']})
            state.update(state='awaiting_approval', artifact_hash=bundle_hash, artifact_ids=[a['id'] for a in package],
                         evidence_ids=[r.id for r in rules], dependencies=dependencies, questions=[], approval=None,
                         updated_at=utcnow(), lease_until=0, attempts=previous['attempts'])
            _span(db, state['id'], 'tool.executed', {'name': 'request_review'},
                  {'artifact_hash': bundle_hash, 'input_hash': state['input_hash'], 'effect_key': effect_key})
            _put(db, 'relay', state['id'], state)
            _manifest(db, state['id'], state['state'])
        return state

    def artifacts(self, run_id: str, scope: Scope | None = None) -> list[dict]:
        state = self.get(run_id, scope)
        artifacts = [self.store.get('artifacts', aid) for aid in state['artifact_ids']]
        if any(a is None or digest(a['content'].encode()) != a['sha256'] for a in artifacts):
            raise RelayError('postcondition', 'An artifact is missing or corrupted.')
        return artifacts

    def approve(self, run_id: str, artifact_hash: str, input_hash: str, scope: Scope | None = None) -> dict:
        state = self.get(run_id, scope)
        parsed_scope = self._authorize(state, scope)
        artifacts = self.artifacts(run_id, scope)
        current_deps = {eid: self.atlas.evidence(parsed_scope, eid) for eid in state['dependencies']}
        stale_sources = any(c is None or c.source_hash != state['dependencies'][eid] for eid, c in current_deps.items())
        with self.store.transaction() as db:
            state = _get(db, 'relay', run_id)
            self._authorize(state, scope)
            if state['state'] == 'succeeded' and state['approval'] and artifact_hash == state['artifact_hash'] and input_hash == state['input_hash']:
                return state
            valid_bundle = bool(artifacts) and digest({'artifacts': {a['name']: a['sha256'] for a in artifacts},
                                                      'input_hash': state['input_hash'],
                                                      'dependencies': state['dependencies']}) == state['artifact_hash']
            if (state['state'] != 'awaiting_approval' or artifact_hash != state['artifact_hash'] or
                    input_hash != state['input_hash'] or stale_sources or not valid_bundle):
                _span(db, run_id, 'approval.validation', {'artifact_hash': artifact_hash, 'input_hash': input_hash},
                      {'approved': False, 'stale_sources': stale_sources}, 'error', 'stale_approval')
                error = True
            elif time.time() > state['deadline_at']:
                state.update(state='failed', error={'code': 'timeout', 'message': 'Approval deadline expired.'})
                _put(db, 'relay', run_id, state)
                _manifest(db, run_id, 'failed')
                _span(db, run_id, 'approval.validation', {}, {'approved': False}, 'error', 'timeout')
                error = True
            else:
                state.update(state='succeeded', approval={'artifact_hash': artifact_hash, 'input_hash': input_hash,
                             'reviewer': 'local-human', 'decision': 'approved', 'at': utcnow()}, updated_at=utcnow())
                _put(db, 'relay', run_id, state)
                _manifest(db, run_id, 'succeeded')
                _span(db, run_id, 'approval.committed', {}, {'approved': True, 'artifact_hash': artifact_hash})
                error = False
        if error:
            raise RelayError('stale_approval', 'Approval rejected: state, artifact, input, sources or deadline changed.')
        return state

    def cancel(self, run_id: str, scope: Scope | None = None) -> dict:
        with self.store.transaction() as db:
            state = _get(db, 'relay', run_id)
            if state is None:
                raise KeyError(run_id)
            self._authorize(state, scope)
            if state['state'] == 'succeeded':
                raise RelayError('terminal_run', 'A completed run cannot be cancelled retroactively.')
            if state['state'] != 'cancelled':
                state.update(state='cancelled', operation_token=None, live_owner=None,
                             lease_until=0, updated_at=utcnow())
                _put(db, 'relay', run_id, state)
                _manifest(db, run_id, 'cancelled')
                _span(db, run_id, 'cancel', {}, {'state': 'cancelled'})
        return state

    def export_artifacts(self, run_id: str, destination: str | Path, scope: Scope | None = None) -> list[str]:
        """A repeatable local projection; same content is not a second effect."""
        target = Path(destination).resolve()
        target.mkdir(parents=True, exist_ok=True)
        paths = []
        for artifact in self.artifacts(run_id, scope):
            if artifact['name'] not in {'requirements.json', 'questions.md', 'handoff.md'}:
                raise RelayError('invalid_args', 'Unexpected artifact filename.')
            path = target / artifact['name']
            if path.is_symlink():
                raise RelayError('permission', 'Artifact destination cannot be a symlink.')
            temporary = target / ('.' + artifact['name'] + '.' + uuid.uuid4().hex + '.tmp')
            temporary.write_text(artifact['content'], encoding='utf-8')
            temporary.replace(path)
            paths.append(str(path))
        return paths

    def run_live(self, provider, brief: dict, scope: Scope | None = None, max_steps: int = 8) -> dict:
        """Opt-in model-proposed tools, with a deterministic checked handoff tool.

        Provider owns network authorization and budgets. No proposal can approve
        artifacts or invoke a tool outside the fixed allowlist.
        """
        if not 1 <= max_steps <= 12:
            raise RelayError('invalid_args', 'Use between 1 and 12 tool steps.')
        state = self._initialize(brief, 'live', scope, 300)
        schemas = {name: args.model_json_schema() for name, args in ARG_MODELS.items()}
        observations: list[dict] = []
        steps = 0
        try:
            while steps < max_steps:
                proposals = provider.propose_tools(state['brief'], observations, schemas)
                if not isinstance(proposals, list) or not proposals:
                    raise RelayError('invalid_args', 'Provider returned no typed tool proposals.')
                for proposal in proposals:
                    if steps >= max_steps:
                        raise RelayError('budget', 'Tool step budget exhausted.')
                    steps += 1
                    output = self.execute_tool(state['id'], proposal, scope)
                    self.store.trace(state['id'], 'model.tool_proposal', {'step': steps},
                                     {'proposal': proposal, 'generation_kind': 'live_provider', 'validation': 'passed'})
                    observations.append({'tool': proposal.get('name'), 'output': output})
                    state = self.get(state['id'], scope)
                    if state['state'] in {'awaiting_input', 'awaiting_approval', 'failed', 'cancelled'}:
                        return self._live_usage(state, provider, steps)
            raise RelayError('budget', 'Tool step budget exhausted without a useful pause.')
        except Exception as exc:
            code = exc.code if isinstance(exc, RelayError) else 'tool_execution'
            self.store.trace(state['id'], 'live.failure', {'steps': steps}, {}, 'error', code)
            # A delayed provider result may belong to an older input or a cancelled
            # operation. Reload and fence the workflow transition in one transaction.
            with self.store.transaction() as db:
                current = _get(db, 'relay', state['id'])
                self._authorize(current, scope)
                owns_current = (current.get('live_owner') == state.get('live_session') and
                                current['revision'] == state['revision'] and
                                current['input_hash'] == state['input_hash'])
                if current['state'] not in TERMINAL and owns_current:
                    current.update(state='failed', live_owner=None, updated_at=utcnow(),
                                   error={'code': code, 'message': str(exc)})
                    _put(db, 'relay', state['id'], current)
                    _manifest(db, state['id'], 'failed')
                state = current
            return self._live_usage(state, provider, steps)

    def _live_usage(self, state: dict, provider, steps: int):
        usage = getattr(provider, 'usage', None)
        if isinstance(usage, BaseModel):
            usage = usage.model_dump()
        if not isinstance(usage, dict):
            usage = {'calls': None, 'input_tokens': None, 'output_tokens': None, 'cost_usd': None}
        with self.store.transaction() as db:
            current = _get(db, 'relay', state['id'])
            if current is None:
                raise KeyError(state['id'])
            if current.get('live_session') != state.get('live_session'):
                return current
            # Usage is still billable after cancellation, but bookkeeping must not
            # restore any workflow fields from the caller's stale checkpoint.
            current.update(usage=usage, tool_steps=max(steps, current.get('tool_steps', 0)))
            _put(db, 'relay', state['id'], current)
            run = _get(db, 'runs', state['id'])
            run.update(usage=usage, status=current['state'], measurement_status='measured')
            _put(db, 'runs', state['id'], run)
        return current


def experiment(store: Store, atlas, mode: str = 'fixture') -> dict:
    start = time.perf_counter()
    relay = Relay(store, atlas)
    incomplete = relay.create({'brand': 'luma', 'objective': 'brand logo banner', 'copy': 'Explore more'}, mode)
    restarted = Relay(Store(store.path), atlas)
    prepared = restarted.resume(incomplete['id'], {'width': 1200, 'height': 628})
    if prepared['state'] != 'awaiting_approval':
        return {'module': 'relay', 'mode': mode, 'status': 'BLOCKED', 'run_id': prepared['id'],
                'reason': prepared.get('error'), 'data_origin': 'synthetic', 'measurement_status': 'measured'}
    old_hash, old_input = prepared['artifact_hash'], prepared['input_hash']
    changed = restarted.resume(prepared['id'], {'copy': 'Explore your next path'})
    stale_rejected = False
    try:
        restarted.approve(changed['id'], old_hash, old_input)
    except RelayError as exc:
        stale_rejected = exc.code == 'stale_approval'
    approved = restarted.approve(changed['id'], changed['artifact_hash'], changed['input_hash'])
    repeated = restarted.resume(changed['id'])
    effects = [e for e in store.list('relay_effects') if e['run_id'] == changed['id']]
    artifacts = restarted.artifacts(changed['id'])
    checks = {'clarification_requested': incomplete['state'] == 'awaiting_input',
              'resume_after_reopen': prepared['state'] == 'awaiting_approval',
              'stale_approval_rejected': stale_rejected, 'approved_after_review': approved['state'] == 'succeeded',
              'repeat_has_no_duplicate_effect': repeated['artifact_hash'] == approved['artifact_hash'] and len(effects) == 2,
              'three_valid_artifacts': len(artifacts) == 3 and all(digest(a['content'].encode()) == a['sha256'] for a in artifacts)}
    report = {'module': 'relay', 'mode': mode, 'data_origin': 'synthetic', 'measurement_status': 'measured',
              'review_status': 'automated_demo_approval', 'status': 'PASS' if all(checks.values()) else 'FAIL',
              'run_id': changed['id'], 'checks': checks, 'passed': sum(checks.values()), 'failed': sum(not v for v in checks.values()),
              'skipped': 0, 'effect_count': len(effects), 'artifact_names': [a['name'] for a in artifacts],
              'elapsed_ms': (time.perf_counter() - start) * 1000, 'usage': {'calls': 0, 'cost_usd': None},
              'limitations': ['Explicit workflow, not model-selected planning.', 'Approval in this experiment is an automated test action, not a human review.',
                              'SQLite content transaction does not guarantee exactly-once external actions.']}
    store.put('reports', 'relay', report)
    return report
