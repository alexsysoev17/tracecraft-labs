'use strict';

// Public synthetic-data UI. Every server-provided string is escaped before HTML insertion.
const LABS = {
  atlas: { name: 'ATLAS', sub: 'Hybrid retrieval', category: 'HYBRID RETRIEVAL LAB', title: 'Find the rule.<br><em>Keep the evidence.</em>', description: 'Compare lexical, dense and hybrid retrieval on the same question. Inspect the source behind every answer, including the gaps.', command: 'make atlas' },
  relay: { name: 'RELAY', sub: 'Agent execution', category: 'AGENT EXECUTION LAB', title: 'From brief<br><em>to a verified handoff.</em>', description: 'Follow a bounded workflow through clarification, evidence and human review. Completion means checked artifacts, not a confident message.', command: 'make relay' },
  sentinel: { name: 'SENTINEL', sub: 'Regression detection', category: 'REGRESSION LAB', title: 'Change one thing.<br><em>Check what breaks.</em>', description: 'Compare actual baseline and candidate outputs with the same evaluator. A critical failure cannot hide inside a better average.', command: 'make sentinel' },
  lens: { name: 'LENS', sub: 'Failure forensics', category: 'FAILURE FORENSICS', title: 'Trace the failure.<br><em>Test the explanation.</em>', description: 'Inspect recorded execution events, isolate evidence and turn an incident into a draft regression case. A hypothesis is not a proven cause.', command: 'make lens' },
  echo: { name: 'ECHO', sub: 'Semantic cache', category: 'SEMANTIC CACHE LAB', title: 'Reuse the answer.<br><em>Recheck the conditions.</em>', description: 'Compare cache policies with explicit scope and provenance checks. Similar wording alone is never permission to reuse an answer.', command: 'make echo' },
  canon: { name: 'CANON', sub: 'Brand benchmark', category: 'BRAND KNOWLEDGE BENCHMARK', title: 'Know the brand.<br><em>Know the limits.</em>', description: 'Evaluate rule application, exceptions, versions and correct abstention across two original fictional brands. Inspect every case and its evidence.', command: 'make canon' },
};
const MODES = {
  fixture: ['Fixture', 'Deterministic test responses · no model generation'],
  local: ['Local', 'Real local embeddings when prepared · extractive answers'],
  replay: ['Replay', 'Previously recorded report · no fresh benchmark'],
};
const state = {
  lab: Object.keys(LABS).includes(location.hash.slice(1)) ? location.hash.slice(1) : 'atlas',
  mode: 'fixture', brand: 'luma', snapshot: 'v2', status: null, errors: {}, busy: {}, data: {}, reports: {}, corpus: [], cases: [], runs: [],
  inputs: { atlasQuery: 'Какой основной цвет бренда?', echoQuery: 'Какой основной цвет бренда?', echoPolicy: 'exact', relayObjective: 'Prepare a launch banner for the new Luma Field collection.', relayCopy: 'Make room for daylight.', relayWidth: '', relayHeight: '', relayRun: '', sentinelCandidate: 'broken', lensRun: '', lensFault: 'invalid_args', canonMethod: 'lexical', canonSplit: 'all', canonCategory: 'all' },
  artifactIndex: 0,
};
const $ = (selector, root = document) => root.querySelector(selector);
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const h = escapeHTML;
const json = value => JSON.stringify(value, null, 2);
const array = value => Array.isArray(value) ? value : [];
const object = value => value && typeof value === 'object' && !Array.isArray(value) ? value : {};
const num = (value, digits = 1) => typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '—';
const titleCase = value => String(value ?? '').replaceAll('_', ' ');
function badge(value, tone) {
  const v = String(value ?? 'not run');
  const detected = /REGRESSION|failed|unsafe|error|rejected|invalid|cancelled/i.test(v) ? 'bad' : /BLOCKED|NOT_|INCONCLUSIVE|conflict|insufficient|awaiting|review|unknown|unavailable/i.test(v) ? 'warn' : /supported|PASS|succeeded|hit|ready|measured/i.test(v) ? '' : 'neutral';
  return `<span class="badge ${h(tone ?? detected)}">${h(v)}</span>`;
}
function empty(title, detail = '', symbol = '↳') { return `<div class="empty-state"><span class="empty-symbol" aria-hidden="true">${h(symbol)}</span><strong>${h(title)}</strong>${h(detail)}</div>`; }
function raw(value, label = 'Inspect raw result') { return `<details class="raw-details"><summary>${h(label)}</summary><pre class="code-block">${h(json(value))}</pre></details>`; }
function metric(label, value, note = '', word = false) { return `<div class="metric"><div class="metric-label">${h(label)}</div><div class="metric-value ${word ? 'word' : ''}">${h(value ?? '—')}</div><div class="metric-note">${h(note)}</div></div>`; }
function metrics(items) { return `<div class="metrics-row">${items.map(i => metric(...i)).join('')}</div>`; }
function field(id, label, value, placeholder = '', type = 'text', extra = '') { return `<div class="field"><label for="${h(id)}">${h(label)}</label><input id="${h(id)}" name="${h(id)}" type="${h(type)}" value="${h(value)}" placeholder="${h(placeholder)}" ${extra}></div>`; }
function option(value, text, selected) { return `<option value="${h(value)}" ${String(value) === String(selected) ? 'selected' : ''}>${h(text)}</option>`; }
function selectField(id, label, options, selected) { return `<div class="field"><label for="${h(id)}">${h(label)}</label><select id="${h(id)}">${options.map(o => option(o[0], o[1], selected)).join('')}</select></div>`; }
function section(title, meta = '') { return `<div class="section-heading"><h2>${h(title)}</h2><small>${h(meta)}</small></div>`; }
function button(label, action, kind = 'primary', extra = '') { return `<button type="button" data-action="${h(action)}" class="${h(kind)}-button" ${state.busy[state.lab] ? 'disabled' : ''} ${extra}>${h(label)}</button>`; }
function notify(message) { const el = $('#toast'); el.textContent = message; el.hidden = false; clearTimeout(notify.timer); notify.timer = setTimeout(() => el.hidden = true, 5000); }

async function api(path, body) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 120000);
  try {
    const response = await fetch(path, { method: body === undefined ? 'GET' : 'POST', headers: body === undefined ? { Accept: 'application/json' } : { 'Content-Type': 'application/json', Accept: 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal });
    const text = await response.text();
    let value;
    try { value = JSON.parse(text); } catch { throw new Error(`Server returned ${response.status} without a JSON response.`); }
    if (!response.ok) {
      const detail = value.detail ?? value.error ?? value.message ?? value;
      throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    }
    return value;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('The request exceeded the browser time limit. Inspect the saved runs before retrying.');
    throw error;
  } finally { clearTimeout(timer); }
}
function scope() { return { brand: state.brand, snapshot: state.snapshot, mode: state.mode }; }
function saveInputs() {
  for (const key of Object.keys(state.inputs)) { const element = document.getElementById(key); if (element) state.inputs[key] = element.value; }
}
async function runAction(task, destination = state.lab) {
  saveInputs(); const lab = state.lab; state.busy[lab] = true; delete state.errors[lab]; render();
  try { const value = await task(); if (destination) state.data[destination] = value; }
  catch (error) { state.errors[lab] = error.message; }
  finally { state.busy[lab] = false; render(); }
}
async function replayOr(path, body) {
  if (state.mode !== 'replay') return api(path, body);
  const result = await api(`/api/reports/${state.lab}`);
  notify('Showing a saved report. No model or experiment was run.');
  return { ...object(result), replay: true };
}
function savedReportContent(value) { return value?.report ?? value?.result ?? value; }
function hero() {
  const lab = LABS[state.lab]; const index = Object.keys(LABS).indexOf(state.lab) + 1;
  return `<section class="hero"><div><div class="eyebrow"><i></i> LAB ${String(index).padStart(2,'0')} / ${h(lab.category)}</div><h1>${lab.title}</h1><p>${h(lab.description)}</p></div><span class="hero-index" aria-hidden="true">${String(index).padStart(2,'0')}</span></section>`;
}
function scopeControls() {
  const scoped=['atlas','echo','relay'].includes(state.lab);
  const brand=scoped?selectField('brand','Corpus',[['luma','Luma Field'],['veyra','Veyra Works']],state.brand):`<div class="field"><label for="brand">Corpus scope</label><select id="brand" disabled><option>${state.lab==='lens'?'From recorded run':'Both public brands'}</option></select></div>`;
  const snapshot=['atlas','echo'].includes(state.lab)?selectField('snapshot','Snapshot',[['v2','v2 · current'],['v1','v1 · historical']],state.snapshot):`<div class="field"><label for="snapshot">Snapshot</label><select id="snapshot" disabled><option>${state.lab==='relay'?'v2 · current':state.lab==='lens'?'From recorded run':'Pinned by each case'}</option></select></div>`;
  return brand+snapshot;
}
function controls() {
  return `<div class="control-bar">${scopeControls()}<div class="field mode-field"><label for="mode">Execution mode</label><select id="mode">${Object.entries(MODES).map(([k,v])=>option(k,v[0],state.mode)).join('')}<option value="live" disabled>Live · CLI opt-in only</option></select></div></div><div class="mode-helper"><strong>${h(MODES[state.mode][1])}</strong><span>ORIGIN: SYNTHETIC · SCOPE: DEMO READER</span></div>`;
}
function toolsPanel() {
  const lab = LABS[state.lab];
  return `<div class="footer-tools"><details class="tool-detail"><summary>01 / REPRODUCE</summary><div class="detail-content">Run this laboratory from the project root.<code>${h(lab.command)}</code><code>make demo</code></div></details><details class="tool-detail"><summary>02 / CONFIG</summary><div class="detail-content">The report records the executed configuration.<code>${h(json(scope()))}</code>${button('Inspect server status','server-status','secondary')}</div></details><details class="tool-detail"><summary>03 / DATA</summary><div class="detail-content">Luma Field and Veyra Works are independently authored, fictional brands. Gold is kept out of retrieval.${button('Inspect source corpus','corpus','secondary')}</div></details><details class="tool-detail"><summary>04 / REPORT</summary><div class="detail-content">Recorded outputs, measured timings and explicit limitations.${button('View saved report','report','secondary')}${button('Download current JSON','download','secondary',state.data[state.lab] ? '' : 'disabled')}</div></details></div>`;
}
function render() {
  $('#navigation').innerHTML = Object.entries(LABS).map(([key,lab],i)=>`<a class="nav-item ${state.lab===key?'active':''}" href="#${key}" ${state.lab===key?'aria-current="page"':''}><span class="nav-number">${String(i+1).padStart(2,'0')}</span><span class="nav-name">${lab.name}<small>${h(lab.sub)}</small></span><span class="nav-arrow" aria-hidden="true">↗</span></a>`).join('');
  $('#breadcrumb-lab').textContent = LABS[state.lab].name;
  document.title = `${LABS[state.lab].name} — TRACECRAFT LABS`;
  const content = state.mode==='replay' ? replayPage() : { atlas: atlasPage, relay: relayPage, sentinel: sentinelPage, lens: lensPage, echo: echoPage, canon: canonPage }[state.lab]();
  $('#main').innerHTML = `${hero()}${controls()}${state.errors[state.lab]?`<div role="alert" class="inline-error">${h(state.errors[state.lab])}</div>`:''}${state.busy[state.lab]?'<div class="loading-strip" role="status" aria-label="Running laboratory"><span class="sr-only">Running laboratory…</span></div>':''}${state.data[state.lab]?.replay?'<div class="notice">RECORDED REPLAY · These are saved outputs, not a new benchmark.</div>':''}${content}${toolsPanel()}`;
  $('#brand').addEventListener('change', e => { saveInputs(); state.brand = e.target.value; if(state.lab!=='relay')delete state.data[state.lab]; render(); });
  $('#snapshot').addEventListener('change', e => { saveInputs(); state.snapshot = e.target.value; if(state.lab!=='relay')delete state.data[state.lab]; render(); });
  $('#mode').addEventListener('change', e => { saveInputs(); state.mode = e.target.value; state.data={}; render(); });
  $('#main').querySelectorAll('form').forEach(form => form.addEventListener('submit', e => { e.preventDefault(); action(form.dataset.submit); }));
  if ($('#canonSplit')) $('#canonSplit').addEventListener('change', () => { saveInputs(); render(); });
  if ($('#canonCategory')) $('#canonCategory').addEventListener('change', () => { saveInputs(); render(); });
}

function replayPage() {
  const data=savedReportContent(state.data[state.lab]);
  let content='';
  if(data?.methods||data?.comparisons) {const comparisons=data.methods??data.comparisons; content=`<div class="table-wrap"><table><thead><tr><th>METHOD</th><th>STATUS</th><th>PASSED</th><th>FAILED</th><th>SKIPPED</th></tr></thead><tbody>${Object.entries(comparisons).map(([name,r])=>`<tr><td>${h(name)}</td><td>${badge(r.status)}</td><td>${h(r.summary?.counts?.passed??'—')}</td><td>${h(r.summary?.counts?.failed??'—')}</td><td>${h(r.summary?.counts?.skipped??'—')}</td></tr>`).join('')}</tbody></table></div>`;}
  else if(data?.policies) content=cacheExperimentTable(data.policies);
  else if(data?.broken) content=`<div class="decision-list">${['broken','normal'].map(name=>`<div class="decision-item"><span>${h(name)} candidate</span><span>${badge(data[name]?.decision)} · ${h(data[name]?.regressions?.length??'—')} regressions</span></div>`).join('')}</div>`;
  else if(data?.diagnosis?.timeline) content=timeline(data.diagnosis.timeline);
  else if(data?.checks) content=`<div class="decision-list">${Object.entries(data.checks).map(([check,value])=>`<div class="decision-item"><span>${h(titleCase(check))}</span><span>${badge(value===true?'PASS':value===false?'FAIL':'NOT_RUN')}</span></div>`).join('')}</div>`;
  return `<section class="panel">${section('Recorded replay','NO NEW COMPUTATION')}<p class="subtle-note">Load the last saved ${LABS[state.lab].name} experiment. Original outputs and timings are shown as recorded; this does not rerun tools or call a model.</p><div class="button-row">${button('Load saved experiment','replay-load','primary')}</div></section><section class="panel">${section('Saved observations',data?String(data.measurement_status??'recorded').toUpperCase():'NOT LOADED')}${data?`${badge(data.status??data.mode??'recorded')}<div style="margin-top:16px">${content}</div>${raw(data,'Inspect complete recorded result')}`:empty('No recording loaded.','A saved report becomes available after the experiment has been executed.')}</section>`;
}
function atlasPage() {
  const data = savedReportContent(state.data.atlas); const answer = data?.answer;
  return `<form class="panel query-box" data-submit="atlas-run">${section('Ask the corpus','SAME QUERY · THREE METHODS')}<div class="query-row"><label class="sr-only" for="atlasQuery">Question for brand corpus</label><input id="atlasQuery" maxlength="2000" value="${h(state.inputs.atlasQuery)}" placeholder="Ask a question about the selected brand…"><button type="submit" class="primary-button" ${state.busy.atlas?'disabled':''}>Compare retrieval <span aria-hidden="true">↗</span></button></div><div class="sample-row"><span>TRY A CASE</span><button type="button" class="chip" data-sample="exact">Exact token</button><button type="button" class="chip" data-sample="paraphrase">Paraphrase</button><button type="button" class="chip" data-sample="unknown">Unknown</button><button type="button" class="chip" data-sample="conflict">Conflict</button></div></form>${metrics([['ANSWER STATE',answer?titleCase(answer.status):'Not run','Grounding, not model confidence',true],['EVIDENCE',answer?.evidence_ids?.length??'—','Sources cited in the answer'],['LATENCY',answer?`${num(answer.latency_ms)} ms`:'—','Observed answer duration'],['MODEL CALLS',answer?.usage?.calls??'—',answer?'Generation: '+(answer.generation_kind??'unknown'):'No run recorded']])}${section('Retrieval comparison','RANKS ARE NOT PROBABILITIES')}<div class="retrieval-grid">${['lexical','dense','hybrid'].map(method=>retrievalColumn(method,data?.[method])).join('')}</div>${answer?answerPanel(answer):`<section class="panel answer-panel">${section('Grounded answer','EXTRACTIVE OUTPUT')}${empty('The evidence comes first.','Run a query to inspect the answer and its cited source spans.')}</section>`}${data?.answer?.retrieval?.required?.length?`<section class="panel">${section('Mandatory constraints','ADDED SEPARATELY FROM TOP-K')}<div class="citation-row">${data.answer.retrieval.required.map(c=>`<button type="button" class="citation" data-evidence="${h(c.id)}" data-brand="${h(c.brand)}">${h(c.title)} ↗</button>`).join('')}</div></section>`:''}`;
}
function retrievalColumn(method, result) {
  const names={lexical:['LEXICAL','SQLite FTS5 · BM25'],dense:['DENSE','Local embedding · cosine'],hybrid:['HYBRID','Reciprocal rank fusion']};
  const hits=array(result?.hits); const blocked=result && !['ready','ok','measured'].includes(result.status||'ready');
  return `<section class="retrieval-column"><div class="column-top"><h3>${names[method][0]}</h3><small>${result?`${num(result.latency_ms)} ms`:'—'}</small></div><div class="column-sub"><span>${names[method][1]}</span><span>${result?`${hits.length} hits`:'NOT RUN'}</span></div><div class="retrieval-list">${blocked?empty(result.status,result.reason??'This retrieval profile is not ready.','∅'):hits.length?hits.map(hit=>{const e=hit.evidence??hit;return `<button class="hit" type="button" data-evidence="${h(e.id)}" data-brand="${h(e.brand)}"><span class="hit-header"><span class="rank">${String(hit.rank??1).padStart(2,'0')} / ${h(e.id)}</span><span>${num(hit.score,4)}</span></span><span class="hit-title">${h(e.title)}</span><span class="hit-excerpt">${h(e.text)}</span></button>`}).join(''):empty(result?'No matching evidence':'Awaiting a query',result?'No source is invented to fill this gap.':'Compare the same question across all three methods.')}</div></section>`;
}
function answerPanel(answer) { return `<section class="panel answer-panel">${section('Grounded answer',`${answer.mode??state.mode} · ${answer.generation_kind??'extractive'}`)}${badge(answer.status)}<p class="answer-text">${h(answer.text)}</p><div class="answer-meta"><span>ORIGIN ${h(answer.data_origin??'unknown')}</span><span>MEASUREMENT ${h(answer.measurement_status??'unknown')}</span><span>REVIEW ${h(answer.review_status??'unknown')}</span></div><div class="citation-row">${array(answer.evidence_ids).map(id=>`<button type="button" class="citation" data-evidence="${h(id)}">${h(id)} ↗</button>`).join('')}</div>${array(answer.claims).length?`<details class="raw-details"><summary>Inspect claims and source quotes</summary>${answer.claims.map(c=>`<p><strong>${h(c.text)}</strong></p><pre class="code-block">${h(c.quote)}\n[${h(c.evidence_id)}]</pre>`).join('')}</details>`:''}</section>`; }

function relayState() { const data = savedReportContent(state.data.relay); return data?.run ?? data; }
function relayPage() {
  const run=relayState(); const artifacts=array(state.data.relay?.artifacts??run?.artifacts); const status=run?.status??run?.state; const id=run?.id??run?.run_id; const missing=array(run?.missing??run?.missing_fields??run?.requirements?.missing); const questions=run?.questions; const ah=run?.artifact_hash??run?.approval?.artifact_hash; const ih=run?.input_hash??run?.approval?.input_hash;
  return `<div class="two-columns wide-left"><section class="panel"><form data-submit="relay-create">${section('Design brief','LOCAL ARTIFACTS ONLY')}<div class="form-grid"><div class="field wide"><label for="relayObjective">Objective</label><textarea id="relayObjective" maxlength="1200" placeholder="What should this banner communicate?">${h(state.inputs.relayObjective)}</textarea></div>${field('relayCopy','Required copy',state.inputs.relayCopy,'Exact approved text','text','maxlength="500"')}${field('relayWidth','Width (px)',state.inputs.relayWidth,'Missing → clarification','number','min="64" max="8192"')}${field('relayHeight','Height (px)',state.inputs.relayHeight,'Missing → clarification','number','min="64" max="8192"')}</div><div class="button-row"><button class="primary-button" type="submit" ${state.busy.relay?'disabled':''}>Start workflow <span aria-hidden="true">↗</span></button></div><p class="subtle-note">Leave a required field empty to test clarification. Outputs are a requirements file, questions and a sourced designer handoff.</p></form></section><section class="panel">${section('Execution state',id?'PERSISTED CHECKPOINT':'NO RUN YET')}${run?`${badge(status)}<p class="run-id">${h(id)}</p><div class="lifecycle">${['queued','running','awaiting_input','awaiting_approval','succeeded'].map(s=>`<span class="${s===status?'current':''}">${h(titleCase(s))}</span>`).join('')}</div><div class="hash-line"><span>ARTIFACT HASH</span><code>${h(ah??'Not created')}</code></div><div class="hash-line"><span>INPUT HASH</span><code>${h(ih??'Not created')}</code></div><div class="button-row">${button('Reload checkpoint','relay-reload','secondary')}${button('Cancel run','relay-cancel','danger',['succeeded','cancelled','failed'].includes(status)?'disabled':'')}</div><p class="subtle-note">The checkpoint survives server restart. Approval applies only to these exact artifact and input hashes.</p>`:empty('A workflow has not started.','Start with an incomplete brief or reopen a saved checkpoint.')+field('relayRun','Saved run identifier',state.inputs.relayRun,'Paste a previous run ID')+`<div class="button-row">${button('Load checkpoint','relay-reload','secondary')}</div>`}</section></div>${status==='awaiting_input'?`<section class="panel">${section('Clarification required','HUMAN INPUT')}${questions?`<p class="subtle-note">${h(typeof questions==='string'?questions:array(questions).map(q=>q.question??q).join(' '))}</p>`:''}<p class="subtle-note">${missing.length?`Missing fields: ${h(missing.join(', '))}. `:''}Update the brief fields above, then resume this same run.</p><div class="button-row">${button('Submit clarification & resume','relay-resume','primary')}</div></section>`:''}${status==='awaiting_approval'?`<section class="panel">${section('Review the handoff','HUMAN APPROVAL')}<p class="subtle-note">Inspect the artifacts below before approving. If the inputs or output changed after this view, stale approval is rejected.</p><div class="button-row">${button('Approve this exact handoff','relay-approve','primary',ah&&ih?'':'disabled')}${button('Refresh artifacts','relay-artifacts','secondary')}</div></section>`:''}<section class="panel">${section('Designer package',artifacts.length?`${artifacts.length} ARTIFACTS`:'VERIFIABLE OUTPUTS')}${artifacts.length?`<div class="artifact-tabs">${artifacts.map((a,i)=>`<button class="chip ${i===state.artifactIndex?'active':''}" type="button" data-artifact="${i}">${h(a.name??a.id)}</button>`).join('')}</div>${artifactView(artifacts[Math.min(state.artifactIndex,artifacts.length-1)])}`:empty('No artifacts have been produced.','The package appears after the brief is complete and the workflow reaches review.')}${run?raw(run,'Inspect persisted run state'):''}</section>`;
}
function artifactView(artifact) { return `<div class="inline-meta"><span>${h(artifact.media_type??'text/plain')}</span><span>SHA256 ${h(artifact.sha256??'unknown')}</span></div><pre class="artifact-content" style="margin-top:12px">${h(artifact.content??json(artifact))}</pre>`; }

function sentinelPage() {
  const data=savedReportContent(state.data.sentinel); const decision=data?.decision??data?.gate??data?.status; const rows=sentinelRows(data); const baseline=data?.baseline?.summary?.counts??{}; const candidate=data?.candidate?.summary?.counts??{};
  return `<form class="panel" data-submit="sentinel-run">${section('Controlled comparison','FIXED CORPUS · FIXED EVALUATOR')}<div class="form-grid">${selectField('sentinelCandidate','Candidate',[['broken','Fault injected · unsupported claim'],['normal','Normal configuration']],state.inputs.sentinelCandidate)}<div class="field"><span class="field-label">Baseline</span><div class="notice" style="margin:0">Evidence-grounded adapter · same public cases</div></div></div><div class="button-row"><button class="primary-button" type="submit" ${state.busy.sentinel?'disabled':''}>Compare actual outputs <span aria-hidden="true">↗</span></button></div><p class="subtle-note">The broken candidate executes a defective behavior. The evaluator must detect the resulting error; a configuration cannot assign itself a score.</p></form>${data?`<div class="verdict ${/REGRESSION|FAIL/.test(String(decision))?'bad':/INCONCLUSIVE|NOT_/.test(String(decision))?'warn':''}"><span class="verdict-icon" aria-hidden="true">${/REGRESSION|FAIL/.test(String(decision))?'↘':'↗'}</span><div><strong>${h(typeof decision==='object'?decision.decision:decision??'NOT_RUN')}</strong><p>${h(data.gate_reason??data.reason??'Exploratory public cases. Passing a gate does not establish statistical improvement.')}</p></div></div>${metrics([['BASELINE',baseline.passed??baseline.pass_count??data.baseline_passed??'—','Cases passing all checks'],['CANDIDATE',candidate.passed??candidate.pass_count??data.candidate_passed??'—','Cases passing all checks'],['REGRESSIONS',array(data.regressions).length||data.regression_count||0,'Review individual cases'],['COMPARABILITY',data.comparability?.comparable===false?'Not comparable':data.comparability?.comparable?'Comparable':'See manifest','Conditions saved with report',true]])}`:''}<section class="panel">${section('Case-by-case evidence',rows.length?`${rows.length} CASE RESULTS`:'NO COMPARISON YET')}${rows.length?comparisonTable(rows):empty('Run a comparison to see the difference.','Both candidate and baseline outputs will be retained for inspection.')}${data?raw(data,'Inspect comparison, configurations and outputs'):''}</section>`;
}
function sentinelRows(data) {
  if (Array.isArray(data?.baseline?.rows)) return data.baseline.rows.map(b=>{const c=array(data?.candidate?.rows).find(c=>c.case_id===b.case_id&&c.repeat===b.repeat);return {case_id:b.case_id,category:b.category,baseline:b,candidate:c,regression:array(data.regressions).some(r=>r.case_id===b.case_id)};});
  return array(data?.cases??data?.results??data?.comparisons);
}
function comparisonTable(rows) {
  return `<div class="table-wrap"><table><thead><tr><th>CASE / CATEGORY</th><th>BASELINE</th><th>CANDIDATE</th><th>OUTCOME</th><th>EVIDENCE</th></tr></thead><tbody>${rows.map((r,i)=>{const b=r.baseline??{},c=r.candidate??{};return `<tr><td>${h(r.case_id??r.id??i+1)}<small>${h(r.category??r.family??'')}</small></td><td>${badge(b.passed===undefined?b.status??r.baseline_passed??'unknown':b.passed?'PASS':'FAIL')}</td><td>${badge(c.passed===undefined?c.status??r.candidate_passed??'unknown':c.passed?'PASS':'FAIL')}</td><td>${badge(r.regression?'REGRESSION':r.decision??r.status??'compared')}</td><td><button type="button" class="table-link" data-case-result="${i}">Inspect outputs ↗</button></td></tr>`}).join('')}</tbody></table></div>`;
}

function lensPage() {
  const outer=savedReportContent(state.data.lens); const data=outer?.diagnosis??outer; const spans=array(data?.spans??data?.timeline??data?.trace); const findings=array(data?.findings??data?.diagnoses); const diagnosis=data?.diagnosis; const runId=data?.run_id??data?.run?.id??state.inputs.lensRun;
  return `<div class="two-columns"><form class="panel" data-submit="lens-inspect">${section('Inspect a recorded run','READ-ONLY TRACE')}<div class="field"><label for="lensRun">Run identifier</label><input id="lensRun" value="${h(state.inputs.lensRun)}" placeholder="Paste an ATLAS, RELAY or ECHO run ID" maxlength="200"></div><div class="button-row"><button type="submit" class="primary-button" ${state.busy.lens?'disabled':''}>Inspect trace <span aria-hidden="true">↗</span></button>${button('Recent runs','runs','secondary')}</div></form><form class="panel" data-submit="lens-fault">${section('Isolated fault injection','SYNTHETIC DEMO ONLY')}${selectField('lensFault','Fault',[['invalid_args','Invalid tool arguments'],['timeout','Deadline / budget timeout'],['omit_evidence','Omitted retrieval evidence']],state.inputs.lensFault)}<div class="button-row"><button type="submit" class="secondary-button" ${state.busy.lens?'disabled':''}>Create diagnostic incident</button></div></form></div><div class="two-columns wide-left"><section class="panel">${section('Execution timeline',spans.length?`${spans.length} OBSERVED EVENTS`:'AWAITING TRACE')}${spans.length?timeline(spans):empty('No trace selected.','Inspect an existing run or execute an isolated fault. Recorded tool calls are not re-executed.')}</section><section class="panel">${section('Diagnostic evidence','SYMPTOM ≠ CAUSE')}${data?`${badge(data.status??diagnosis?.status??'recorded')}<p class="run-id">${h(runId)}</p>${diagnosis?`<p class="answer-text">${h(diagnosis.symptom??diagnosis.summary??diagnosis.category??(typeof diagnosis==='string'?diagnosis:''))}</p>`:''}${findings.map(f=>`<div class="notice ${f.confirmed?'':'warn'}"><strong>${h(f.category??f.kind??f.classification??'Finding')}</strong><br>${h(f.symptom??f.message??f.description??f.hypothesis??'')}<br><small>${h(f.certainty??f.evidence_status??'hypothesis')} ${array(f.evidence_span_ids??f.span_ids??f.evidence).map(x=>h(typeof x==='string'?x:json(x))).join(' · ')}</small></div>`).join('')}<p class="subtle-note">A draft captures the incident and evidence. Expected behavior needs separate confirmation before becoming benchmark gold.</p><div class="button-row">${button('Create regression draft','lens-draft','primary',runId?'':'disabled')}</div>${data.draft?raw(data.draft,'Inspect regression case draft'):''}`:empty('Evidence will appear here.','No cause is asserted before examining recorded events.')}</section></div>${data?raw(data,'Inspect complete forensic report'):''}`;
}
function timeline(spans) { return `<ol class="timeline">${spans.map(s=>`<li class="${s.error||s.status==='error'?'failed':''}"><div class="timeline-head"><h3>${h(s.stage??s.name??'event')}</h3>${badge(s.status??'recorded')}</div><p class="run-id">${h(s.id??'')}</p><time>${h(s.timestamp??s.started_at??'')}</time>${s.error?`<p style="color:var(--red)">${h(s.error)}</p>`:''}<details><summary>Inputs, outputs &amp; validation</summary><pre class="code-block">${h(json({inputs:s.inputs,outputs:s.outputs,parent_id:s.parent_id}))}</pre></details></li>`).join('')}</ol>`; }

function echoPage() {
  const data=savedReportContent(state.data.echo); const result=data?.answer?data:null; const answer=result?.answer; const experiment=data?.policies??data?.results??data?.comparison;
  return `<form class="panel query-box" data-submit="echo-run">${section('Ask with a cache policy','READ-ONLY KNOWLEDGE ANSWERS')}<div class="query-row"><label class="sr-only" for="echoQuery">Cache query</label><input id="echoQuery" value="${h(state.inputs.echoQuery)}" placeholder="Ask a brand question…" maxlength="2000"><button type="submit" class="primary-button" ${state.busy.echo?'disabled':''}>Run query <span aria-hidden="true">↗</span></button></div><div class="button-row">${selectField('echoPolicy','Policy',[['off','Off · control'],['exact','Exact'],['semantic','Semantic · local embeddings']],state.inputs.echoPolicy)}${button('Compare all policies','echo-experiment','secondary')}</div><p class="subtle-note">Repeat the same question for an exact hit. Change brand, version, numbers or negation to inspect reuse boundaries. Semantic lookup requires the prepared local model.</p></form>${metrics([['CACHE DECISION',result?result.decision??(result.hit?'HIT · '+(result.hit_type??'cache'):'MISS'):'Not run','Each decision includes a reason',true],['MODEL CALLS',result?.llm_calls??answer?.usage?.calls??'—','Actual provider calls'],['END-TO-END',result?`${num(result.latency_ms??result.total_latency_ms??answer?.latency_ms)} ms`:'—','Lookup + verification + answer'],['POLICY',result?.policy??'—','No simulated delay',true]])}<div class="two-columns"><section class="panel">${section('Reuse decision','SCOPE + CONTENT + PROVENANCE')}${result?`<div class="decision-list">${Object.entries({decision:result.decision??(result.hit?'HIT · '+(result.hit_type??'cache'):'MISS'),reason:result.reason??result.cache_reason??'See raw result',policy:result.policy??state.inputs.echoPolicy,similarity:result.similarity,namespace:result.namespace,entry:result.entry_id??result.cache_entry_id}).filter(([,v])=>v!==undefined).map(([k,v])=>`<div class="decision-item"><span>${h(titleCase(k))}</span><span>${h(typeof v==='object'?json(v):v)}</span></div>`).join('')}</div>${raw(result,'Inspect cache decision')}`:empty('No lookup has been measured.','Supported answers with known dependencies may enter the cache. Actions and approvals never do.')}</section><section class="panel">${section('Cache boundaries','CONSERVATIVE BY DESIGN')}<div class="decision-list"><div class="decision-item"><span>Brand / snapshot</span><span>Must match</span></div><div class="decision-item"><span>Permissions / context</span><span>Must remain compatible</span></div><div class="decision-item"><span>Numbers / codes / negation</span><span>Checked before reuse</span></div><div class="decision-item"><span>Source dependencies</span><span>Revalidated on hit</span></div><div class="decision-item"><span>Unknown price</span><span>null, never zero</span></div></div></section></div>${answer?answerPanel(answer):''}${experiment?`<section class="panel">${section('Policy experiment','ACTUAL NO-CACHE CONTROL')}${cacheExperimentTable(experiment)}${raw(data,'Inspect all cache observations')}</section>`:''}`;
}
function cacheExperimentTable(experiment) {
  const rows=Array.isArray(experiment)?experiment:Object.entries(object(experiment)).map(([policy,v])=>({...object(v),policy}));
  return `<div class="table-wrap"><table><thead><tr><th>POLICY</th><th>REQUESTS</th><th>HITS</th><th>FALSE HITS</th><th>ANSWER CALLS</th><th>TOTAL TIME</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${h(r.policy??r.name??'—')}</td><td>${h(r.requests??r.count??'—')}</td><td>${h(r.hits??'—')}</td><td>${h(r.false_hits??'—')}</td><td>${h(r.answer_calls??r.actual_calls??r.calls??'—')}</td><td>${num(r.latency_ms??r.total_latency_ms)} ms</td></tr>`).join('')}</tbody></table></div>`;
}

function canonPage() {
  const data=savedReportContent(state.data.canon); const cases=state.cases; const categories=[...new Set(cases.map(c=>c.category))].sort(); const shown=cases.filter(c=>(state.inputs.canonSplit==='all'||c.split===state.inputs.canonSplit)&&(state.inputs.canonCategory==='all'||c.category===state.inputs.canonCategory)); const results=array(data?.rows??data?.results??data?.cases); const slices=data?.summary?.groups??data?.slices??data?.by_category; const summary=data?.summary?.counts??data?.summary??data?.metrics??data;
  return `<form class="panel" data-submit="canon-run">${section('Evaluate a retrieval configuration','GOLD IS NEVER INDEXED')}<div class="section-row">${selectField('canonMethod','Retrieval method',[['lexical','Lexical · BM25'],['full_pack','Full compact rule pack'],['dense','Dense · local embeddings'],['hybrid','Hybrid · RRF']],state.inputs.canonMethod)}<div><button class="primary-button" type="submit" ${state.busy.canon?'disabled':''}>Run benchmark <span aria-hidden="true">↗</span></button><p class="subtle-note">Public cases · machine-authored gold · exploratory findings</p></div></div></form>${metrics([['CASES',data?summary?.count??summary?.total??results.length:'Not run','Executed cases, not corpus size',!data],['PASSED',data?summary?.passed??'—':'—','All applicable checks'],['FAILED',data?summary?.failed??'—':'—','Inspect slices and outputs'],['SKIPPED / BLOCKED',data?summary?.skipped??summary?.blocked??'—':'—','Never counted as passed']])}${slices?`<section class="panel">${section('Benchmark slices','QUALITY IS NOT ONE NUMBER')}${slicesTable(slices)}</section>`:''}<section class="panel">${section('Case explorer',`${cases.length} PUBLIC CASES`)}<div class="form-grid" style="margin-bottom:16px">${selectField('canonSplit','Dataset split',[['all','All splits'],['development','Development'],['validation','Validation'],['test','Public test']],state.inputs.canonSplit)}${selectField('canonCategory','Category',[['all','All categories'],...categories.map(c=>[c,titleCase(c)])],state.inputs.canonCategory)}</div>${shown.length?`<div class="table-wrap"><table><thead><tr><th>CASE</th><th>QUESTION / BRAND</th><th>CATEGORY</th><th>SPLIT</th><th>EXPECTED</th><th>RESULT</th></tr></thead><tbody>${shown.map(c=>{const r=results.find(v=>(v.case_id??v.id)===c.id);return `<tr><td><button type="button" class="table-link" data-gold="${h(c.id)}">${h(c.id)} ↗</button></td><td>${h(c.query)}<small>${h(c.brand)} · ${h(c.snapshot)} · ${h(c.locale)}</small></td><td>${h(titleCase(c.category))}</td><td>${h(c.split)}</td><td>${badge(c.expected_status)}</td><td>${r?badge(r.passed===true?'PASS':r.passed===false?'FAIL':'NOT_RUN'):badge('NOT_RUN')}</td></tr>`}).join('')}</tbody></table></div>`:empty(cases.length?'No cases match these filters.':'Loading public cases…','Cases include facts, exceptions, versions, conflicts and denied sources.')}${data?raw(data,'Inspect benchmark outputs and evaluator checks'):''}</section>`;
}
function slicesTable(slices) {
  const rows=Array.isArray(slices)?slices:Object.entries(object(slices)).map(([category,v])=>({...object(v),category}));
  return `<div class="table-wrap"><table><thead><tr><th>SLICE</th><th>CASES</th><th>PASSED</th><th>FAILED</th><th>SKIPPED</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${h(titleCase(r.category??r.name??r.slice??''))}</td><td>${h(r.count??r.total??r.attempts??'—')}</td><td>${h(r.passed??'—')}</td><td>${h(r.failed??'—')}</td><td>${h(r.skipped??'—')}</td></tr>`).join('')}</tbody></table></div>`;
}

function relayBrief() {
  return { brand: state.brand, objective: state.inputs.relayObjective, copy: state.inputs.relayCopy,
    width: state.inputs.relayWidth === '' ? null : Number(state.inputs.relayWidth), height: state.inputs.relayHeight === '' ? null : Number(state.inputs.relayHeight) };
}
function relayAnswers() { const brief=relayBrief(); delete brief.brand; return brief; }
function currentRelayId() { const run=relayState(); return run?.id??run?.run_id??state.inputs.relayRun; }
async function withArtifacts(run) {
  const id=run?.id??run?.run_id;
  if (!id) return run;
  state.inputs.relayRun=id;
  if (run.brief) {
    state.inputs.relayObjective=run.brief.objective??'';
    state.inputs.relayCopy=run.brief.copy??'';
    state.inputs.relayWidth=run.brief.width??'';
    state.inputs.relayHeight=run.brief.height??'';
    state.brand=run.brief.brand??state.brand;
  }
  try { const artifacts=await api(`/api/relay/${encodeURIComponent(id)}/artifacts`); return {...run,artifacts:array(artifacts?.artifacts??artifacts)}; }
  catch { return run; }
}
async function action(name) {
  saveInputs();
  switch(name) {
    case 'replay-load': return runAction(()=>replayOr('',{}));
    case 'atlas-run': return runAction(()=>replayOr('/api/atlas',{...scope(),query:state.inputs.atlasQuery}));
    case 'relay-create': return runAction(async()=>withArtifacts(await replayOr('/api/relay',{brief:relayBrief(),mode:state.mode})));
    case 'relay-reload': return runAction(async()=>withArtifacts(await api(`/api/relay/${encodeURIComponent(currentRelayId())}`)));
    case 'relay-artifacts': return runAction(async()=>withArtifacts(relayState()));
    case 'relay-resume': return runAction(async()=>withArtifacts(await api(`/api/relay/${encodeURIComponent(currentRelayId())}/resume`,{answers:relayAnswers()})));
    case 'relay-cancel': return runAction(async()=>withArtifacts(await api(`/api/relay/${encodeURIComponent(currentRelayId())}/cancel`,{})));
    case 'relay-approve': { const run=relayState(); return runAction(async()=>withArtifacts(await api(`/api/relay/${encodeURIComponent(currentRelayId())}/approve`,{artifact_hash:run.artifact_hash,input_hash:run.input_hash}))); }
    case 'sentinel-run': return runAction(()=>replayOr('/api/sentinel',{candidate:state.inputs.sentinelCandidate,mode:state.mode}));
    case 'lens-inspect': return runAction(()=>replayOr('/api/lens',{run_id:state.inputs.lensRun,mode:state.mode}));
    case 'lens-fault': return runAction(()=>replayOr('/api/lens',{fault:state.inputs.lensFault,mode:state.mode}));
    case 'lens-draft': return runAction(async()=>{const current=savedReportContent(state.data.lens);const runId=current?.run_id??current?.manifest?.id??state.inputs.lensRun;const draft=await api(`/api/lens/${encodeURIComponent(runId)}/draft`,{});return {...current,draft};});
    case 'echo-run': return runAction(()=>replayOr('/api/echo',{...scope(),query:state.inputs.echoQuery,policy:state.inputs.echoPolicy}));
    case 'echo-experiment': return runAction(()=>replayOr('/api/echo/experiment',{mode:state.mode}));
    case 'canon-run': return runAction(()=>replayOr('/api/canon',{mode:state.mode,method:state.inputs.canonMethod}));
    case 'corpus': return showCorpus();
    case 'server-status': return showDialog('SERVER STATUS', '<h2>Runtime capabilities</h2>'+raw(state.status,'Inspect actual server state'));
    case 'report': return showReport();
    case 'download': return downloadCurrent();
    case 'runs': return showRuns();
    default: return;
  }
}
function showDialog(label, content) {
  $('#inspector-label').textContent=label;
  $('#inspector-body').innerHTML=content;
  if (!$('#inspector').open) $('#inspector').showModal();
}
function showModes() {
  showDialog('EXECUTION MODES','<h2>What actually ran?</h2><p>Mode, data origin, measurement and review are independent fields. Synthetic data can produce real measurements; fixture success does not prove model reliability.</p>'+[
    ['fixture','Deterministic test responses and local mechanics. No generative model request.','Suitable for the first run and offline CI.'],
    ['local','Real prepared embeddings, indexing and search. Without a generator, the answer is explicitly extractive.','Run make models first. Unavailable models block dense search.'],
    ['replay','Displays previously recorded outputs and traces. No fresh inference or side effects.','Do not interpret replay timing as a new benchmark.'],
    ['live','Real, bounded calls to an explicitly configured provider. Disabled in this browser workspace.','Use the documented opt-in CLI and explicit limits.'],
  ].map(([name,description,note])=>`<div class="mode-card"><strong>${h(name)}</strong><div><p>${h(description)}</p><small>${h(note)}</small></div></div>`).join(''));
}
async function showEvidence(id, brand=state.brand) {
  showDialog('EVIDENCE INSPECTOR',empty('Loading source…'));
  try {
    const result=await api(`/api/evidence/${encodeURIComponent(id)}?brand=${encodeURIComponent(brand)}&snapshot=${encodeURIComponent(state.snapshot)}`);const e=result?.evidence??result;
    showDialog('EVIDENCE INSPECTOR',`<h2>${h(e.title??e.id)}</h2><div class="inline-meta">${badge(e.status)}${badge(e.authority)}${badge(e.polarity)}${badge(e.data_origin)}</div><div class="source-text">${h(e.text)}</div><dl>${Object.entries({id:e.id,document:e.document_id,section:e.section,brand:e.brand,snapshot:e.snapshot,kind:e.kind,mandatory:e.mandatory,rule_key:e.rule_key,span:`${e.start??0}–${e.end??0}`,source_hash:e.source_hash}).map(([key,val])=>`<dt>${h(titleCase(key))}</dt><dd>${h(val)}</dd>`).join('')}</dl><p>A valid source reference proves that the text exists. Claim support is checked separately.</p>`);
  } catch(error) { showDialog('EVIDENCE INSPECTOR',`<h2>Source unavailable</h2><p>${h(error.message)}</p>`); }
}
async function showCorpus() {
  showDialog('PUBLIC DATA',empty('Loading selected corpus…'));
  try {const data=await api(`/api/corpus?brand=${encodeURIComponent(state.brand)}&snapshot=${encodeURIComponent(state.snapshot)}`);const items=array(data?.chunks??data?.evidence??data?.documents??data);state.corpus=items;
    showDialog('PUBLIC DATA',`<h2>${state.brand==='luma'?'Luma Field':'Veyra Works'}</h2><p>Original fictional brand · ${h(state.snapshot)} · only sources accessible to the server-assigned demo reader are shown.</p>${items.length?`<div class="table-wrap"><table><thead><tr><th>SOURCE</th><th>KIND / STATUS</th></tr></thead><tbody>${items.map(e=>`<tr><td><button type="button" class="table-link" data-evidence="${h(e.id)}" data-brand="${h(e.brand)}">${h(e.title??e.id)} ↗</button><small>${h(e.id)}</small></td><td>${badge(e.kind)} ${badge(e.status)}</td></tr>`).join('')}</tbody></table></div>`:empty('No eligible sources.',data?.status??'Try another snapshot.')}${raw(data,'Inspect corpus metadata')}`);
  } catch(error) {showDialog('PUBLIC DATA',`<h2>Corpus unavailable</h2><p>${h(error.message)}</p>`);}
}
async function showReport() {
  showDialog('RECORDED REPORT',empty('Loading report…'));
  try { const data=await api(`/api/reports/${state.lab}`);state.reports[state.lab]=data;showDialog('RECORDED REPORT',`<h2>${LABS[state.lab].name} / saved result</h2><p>This is a stored report. It does not execute another experiment.</p><pre class="code-block">${h(json(data))}</pre>`); }
  catch(error) {showDialog('RECORDED REPORT',`<h2>No saved report available</h2><p>${h(error.message)}</p><p>Run the laboratory experiment, then inspect its recorded report.</p>`);}
}
async function showRuns() {
  showDialog('RECENT RUNS',empty('Loading runs…'));
  try {const data=await api('/api/runs');state.runs=array(data?.runs??data);showDialog('RECENT RUNS',`<h2>Recorded executions</h2>${state.runs.length?`<div class="table-wrap"><table><thead><tr><th>RUN</th><th>MODULE / MODE</th><th>STATE</th></tr></thead><tbody>${state.runs.slice(0,40).map(r=>`<tr><td><button type="button" class="table-link" data-run="${h(r.id??r.run_id)}">${h(r.id??r.run_id)} ↗</button><small>${h(r.started_at??'')}</small></td><td>${h(r.module)}<small>${h(r.mode)}</small></td><td>${badge(r.status)}</td></tr>`).join('')}</tbody></table></div>`:empty('No runs yet.','Run any laboratory to create traceable execution records.')}`);}
  catch(error){showDialog('RECENT RUNS',`<h2>Runs unavailable</h2><p>${h(error.message)}</p>`);}
}
function downloadCurrent() {
  const data=state.data[state.lab];if(!data)return;
  const blob=new Blob([json(data)+'\n'],{type:'application/json'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=`tracecraft-${state.lab}-${state.mode}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);notify('Downloaded the current public result.');
}
async function refreshStatus() {
  try {state.status=await api('/api/status');$('#connection-dot').classList.remove('offline');$('#connection-label').textContent='Local server connected';}
  catch(error){state.status={status:'unavailable',error:error.message};$('#connection-dot').classList.add('offline');$('#connection-label').textContent='Server unavailable';}
}
async function loadCases() {
  try { const result=await api('/api/cases');state.cases=array(result?.cases??result);if(state.lab==='canon')render(); }
  catch(error){if(state.lab==='canon'){state.errors.canon=error.message;render();}}
}

window.addEventListener('hashchange',()=>{saveInputs();const lab=location.hash.slice(1);state.lab=Object.keys(LABS).includes(lab)?lab:'atlas';render();window.scrollTo({top:0});});
document.addEventListener('click',event=>{
  const el=event.target.closest('button');if(!el)return;
  if(el.dataset.action){action(el.dataset.action);return;}
  if(el.dataset.evidence){showEvidence(el.dataset.evidence,el.dataset.brand||state.brand);return;}
  if(el.dataset.sample){const sample={exact:'Какой точный код основного цвета?',paraphrase:'Как много свободного места нужно вокруг логотипа?',unknown:'Кто генеральный директор бренда?',conflict:'Какой цвет ленты стартовой упаковки?'};state.inputs.atlasQuery=sample[el.dataset.sample];$('#atlasQuery').value=state.inputs.atlasQuery;$('#atlasQuery').focus();return;}
  if(el.dataset.artifact!==undefined){saveInputs();state.artifactIndex=Number(el.dataset.artifact);render();return;}
  if(el.dataset.caseResult!==undefined){const data=savedReportContent(state.data.sentinel);const rows=sentinelRows(data);const value=rows[Number(el.dataset.caseResult)];showDialog('COMPARISON EVIDENCE',`<h2>${h(value?.case_id??'Case comparison')}</h2><pre class="code-block">${h(json(value))}</pre>`);return;}
  if(el.dataset.gold){const c=state.cases.find(c=>c.id===el.dataset.gold);const result=array(savedReportContent(state.data.canon)?.rows).find(r=>r.case_id===el.dataset.gold);showDialog('BENCHMARK CASE',`<h2>${h(c?.id)}</h2><p>${h(c?.query)}</p>${badge(c?.review_status)}<p>Gold is machine-authored and checked against synthetic source documents. It is not expert-certified.</p><pre class="code-block">${h(json(c))}</pre>${result?raw(result,'Inspect actual answer and checks'):''}`);return;}
  if(el.dataset.run){$('#inspector').close();state.inputs.lensRun=el.dataset.run;if(state.lab!=='lens'){state.lab='lens';location.hash='lens';}render();action('lens-inspect');}
});
$('#close-inspector').addEventListener('click',()=>$('#inspector').close());
$('#inspector').addEventListener('click',event=>{if(event.target===$('#inspector')){const box=$('#inspector').getBoundingClientRect();if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)$('#inspector').close();}});
$('#mode-guide').addEventListener('click',showModes);
$('#show-corpus').addEventListener('click',showCorpus);
$('#refresh-status').addEventListener('click',async()=>{await refreshStatus();notify('Server status refreshed.');});
render();refreshStatus();loadCases();
