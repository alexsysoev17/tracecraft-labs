"""Independent importer review: provenance, path safety and no silent OCR."""
import hashlib
import json

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from tracecraft.core import ingest


@pytest.fixture
def environment(tmp_path, monkeypatch):
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'private').mkdir()
    source = tmp_path / 'source'
    source.mkdir()
    monkeypatch.setattr(ingest, 'ROOT', project)
    return source, project


def sha(value):
    return hashlib.sha256(value).hexdigest()


def akella_fixture(root, record_updates=None, extra_records=None):
    base = root / 'data/brands/stc'
    base.mkdir(parents=True)
    source_bytes = b'# Original explicit test rule\nKeep the wordmark unchanged.\n'
    (base / 'rule.md').write_bytes(source_bytes)
    record = {'id': 'rule-1', 'kind': 'rule', 'title': 'Wordmark', 'body': 'Keep the wordmark unchanged.',
              'status': 'reviewed', 'authority': 'explicit', 'polarity': 'neutral', 'scope': 'test only',
              'evidence': [{'nodeId': '1:1', 'file': 'rule.md', 'fileSha256': sha(source_bytes)}],
              'links': [], 'review': {'reviewer': 'fixture', 'status': 'reviewed'}}
    record.update(record_updates or {})
    (base / 'source.json').write_text(json.dumps({'nodeIds': ['1:1']}))
    (base / 'records.json').write_text(json.dumps([record, *(extra_records or [])]))
    catalog = {'brand': 'stc', 'name': 'Synthetic schema fixture', 'snapshot': 'test-snapshot',
               'source': 'source.json', 'records': 'records.json', 'resources': []}
    (base / 'catalog.json').write_text(json.dumps(catalog))
    return base, record, catalog


def test_safe_file_rejects_absolute_traversal_and_symlinks(environment, tmp_path):
    source, _ = environment
    outside = tmp_path / 'outside.txt'
    outside.write_text('Do not import')
    (source / 'linked.txt').symlink_to(outside)
    (source / 'directory').symlink_to(tmp_path, target_is_directory=True)
    for relative in ('../outside.txt', str(outside), 'linked.txt', 'directory/outside.txt'):
        with pytest.raises(ValueError):
            ingest.safe_file(source, relative)


def test_document_import_preserves_original_hash_and_private_origin(environment):
    source, project = environment
    document = source / 'rules.md'
    document.write_text('# Rule\nKeep one logo.\n\nException: packaging uses two.\n')
    before = document.read_bytes()
    report = ingest.import_document(source, 'rules.md')
    assert report['source_unchanged'] and report['data_origin'] == 'private'
    assert document.read_bytes() == before
    assert report['document']['sha256'] == sha(before)
    target = next((project / 'private/imports').iterdir())
    chunks = json.loads((target / 'chunks.json').read_text())
    assert chunks and all(c['data_origin'] == 'private' and c['status'] == 'unreviewed' and c['authority'] == 'inferred' for c in chunks)
    assert 'Exception' in chunks[0]['text']


def test_import_rejects_public_destination_and_existing_directory(environment):
    source, project = environment
    (source / 'rules.md').write_text('# Rule\nTest only.')
    with pytest.raises(ValueError, match='private'):
        ingest.import_document(source, 'rules.md', destination=project / 'public')
    existing = project / 'private/existing'
    existing.mkdir()
    with pytest.raises(FileExistsError):
        ingest.import_document(source, 'rules.md', destination=existing)


def test_size_bound_is_checked_before_import(environment, monkeypatch):
    source, project = environment
    (source / 'rules.md').write_text('x' * 60)
    monkeypatch.setattr(ingest, 'MAX_FILE', 32)
    with pytest.raises(ValueError, match='oversized'):
        ingest.import_document(source, 'rules.md')
    assert list((project / 'private').iterdir()) == []


def test_missing_private_source_is_explicit_without_copy(environment):
    source, project = environment
    report = ingest.import_akella(source)
    assert report == {'status': 'MISSING_PRIVATE_SOURCE', 'brand': 'stc', 'imported': False, 'verified': False}
    assert list((project / 'private').iterdir()) == []


def test_akella_valid_bundle_preserves_provenance_and_hashes(environment):
    source, project = environment
    base, record, _ = akella_fixture(source)
    before = {path.name: sha(path.read_bytes()) for path in base.iterdir()}
    report = ingest.import_akella(source)
    assert report['status'] == 'IMPORTED_PRIVATE_SOURCE'
    assert report['source_hashes_before'] == report['source_hashes_after']
    assert before == {path.name: sha(path.read_bytes()) for path in base.iterdir()}
    target = next((project / 'private/imports').iterdir())
    imported = json.loads((target / 'records.json').read_text())
    assert imported == [record]
    assert report['embedding_status'] == 'NOT_INDEXED'


def test_akella_corrupt_hash_rejected_before_copy(environment):
    source, project = environment
    base, _, _ = akella_fixture(source)
    (base / 'rule.md').write_text('Tampered source')
    with pytest.raises(ValueError, match='hash'):
        ingest.import_akella(source)
    assert list((project / 'private').iterdir()) == []


def test_akella_catalog_traversal_and_brand_symlink_rejected(environment, tmp_path):
    source, _ = environment
    base, _, catalog = akella_fixture(source)
    catalog['source'] = '../../../outside.json'
    (base / 'catalog.json').write_text(json.dumps(catalog))
    with pytest.raises(ValueError, match='Unsafe'):
        ingest.import_akella(source)
    # Explicit brand folder symlinks cannot redirect the importer to another tree.
    other = tmp_path / 'other'
    other.mkdir()
    akella_fixture(other)
    (source / 'data/brands/linked').symlink_to(other / 'data/brands/stc', target_is_directory=True)
    with pytest.raises(ValueError, match='Symlink'):
        ingest.import_akella(source, 'linked')


def test_conflicting_declared_hashes_cannot_be_overwritten(environment):
    source, _ = environment
    base, record, _ = akella_fixture(source)
    bad = {**record, 'id': 'rule-bad', 'evidence': [{'nodeId': '1:1', 'file': 'rule.md', 'fileSha256': '0' * 64}]}
    (base / 'records.json').write_text(json.dumps([bad, record]))
    with pytest.raises(ValueError, match='[Hh]ash'):
        ingest.import_akella(source)


@pytest.mark.parametrize('updates', [
    {'kind': 'unsupported'}, {'polarity': 'not-a-polarity'}, {'kind': 'example'}, {'kind': 'asset'},
])
def test_akella_verified_requires_the_actual_record_contract(environment, updates):
    source, _ = environment
    akella_fixture(source, record_updates=updates)
    with pytest.raises(ValueError):
        ingest.import_akella(source)


def test_symlinked_private_destination_cannot_redirect_import(environment, tmp_path):
    source, project = environment
    (project / 'private').rmdir()
    outside = tmp_path / 'outside-private'
    outside.mkdir()
    (project / 'private').symlink_to(outside, target_is_directory=True)
    (source / 'rules.md').write_text('# Rule\nNo outside write.')
    with pytest.raises(ValueError, match='[Ss]ymlink'):
        ingest.import_document(source, 'rules.md')
    assert list(outside.iterdir()) == []


def test_image_only_pdf_is_explicit_and_no_ocr_is_invented(environment):
    source, project = environment
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=200)
    writer.write(source / 'blank.pdf')
    report = ingest.import_document(source, 'blank.pdf')
    assert report['status'] == 'IMAGE_ONLY_PDF_NO_OCR'
    assert report['chunks'] == 0
    assert report['document']['metadata']['ocr'] is False
    target = next((project / 'private/imports').iterdir())
    assert json.loads((target / 'chunks.json').read_text()) == []


def test_pdf_text_layer_retains_page_provenance(environment):
    source, project = environment
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
    stream = DecodedStreamObject()
    stream.set_data(b'BT /F1 12 Tf 20 100 Td (Keep one logo.) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(stream)
    writer.write(source / 'text.pdf')
    report = ingest.import_document(source, 'text.pdf')
    assert report['status'] == 'ready' and report['chunks'] > 0
    target = next((project / 'private/imports').iterdir())
    chunks = json.loads((target / 'chunks.json').read_text())
    assert chunks[0]['section'] == 'Page 1'
    assert 'Keep one logo.' in chunks[0]['text']


def test_section_split_preserves_links_and_exact_offsets():
    text = '# Rule and exception\n' + ('A long scoped instruction.\n' * 20) + '\nException: only for print.\n'
    chunks = ingest.chunk_text(text, 'source', 'luma', 'v2', sha(text.encode()), max_chars=160)
    assert len(chunks) > 1
    ids = {chunk.id for chunk in chunks}
    for chunk in chunks:
        assert chunk.text == text[chunk.start:chunk.end]
        assert set(chunk.links) == ids - {chunk.id}


def test_http_boundary_rejects_cross_origin_host_oversize_and_client_scope(tmp_path):
    from fastapi.testclient import TestClient
    from tracecraft.api.app import create_app
    from tracecraft.core.store import Store
    store = Store(tmp_path / 'api.sqlite')
    client = TestClient(create_app(store))
    payload = {'query': 'logo', 'brand': 'luma', 'mode': 'fixture'}
    assert client.post('/api/atlas', json=payload, headers={'origin': 'https://untrusted.example'}).status_code == 403
    assert client.post('/api/atlas', json=payload, headers={'host': 'untrusted.example'}).status_code == 403
    assert client.post('/api/atlas', content='{}', headers={'content-type': 'text/plain'}).status_code == 415
    assert client.post('/api/atlas', content='x' * 66000, headers={'content-type': 'application/json'}).status_code == 413
    assert client.post('/api/atlas', json={**payload, 'tenant': 'other'}).status_code == 422
    assert client.post('/api/atlas', json={**payload, 'permissions': ['restricted']}).status_code == 422
    assert store.list('runs') == []


def test_http_traces_and_lens_cannot_expose_other_tenant_or_private_origin(tmp_path):
    from fastapi.testclient import TestClient
    from tracecraft.api.app import create_app
    from tracecraft.core.models import Scope
    from tracecraft.core.store import Store
    store = Store(tmp_path / 'api-private.sqlite')
    private_run = store.new_run('atlas', 'fixture', {'scope': Scope(tenant='other').model_dump()})
    store.trace(private_run['id'], 'private_source', {}, {'text': 'TRACECRAFT_PRIVATE tenant content'})
    external_run = store.new_run('lens-import', 'replay', {'scope': Scope().model_dump()})
    external_run['data_origin'] = 'external'
    store.put('runs', external_run['id'], external_run)
    client = TestClient(create_app(store))
    for run in (private_run, external_run):
        assert client.get('/api/runs/' + run['id']).status_code == 404
        assert client.post('/api/lens', json={'run_id': run['id']}).status_code == 404
        assert client.post('/api/lens/' + run['id'] + '/draft', json={}).status_code == 404
    assert client.get('/api/runs').json()['runs'] == []
    assert client.get('/..%2Fsrc%2Ftracecraft%2Fcore%2Fstore.py').status_code == 404


def test_http_live_never_calls_a_provider(tmp_path):
    from fastapi.testclient import TestClient
    from tracecraft.api.app import create_app
    from tracecraft.core.store import Store
    store = Store(tmp_path / 'api-live.sqlite')
    client = TestClient(create_app(store))
    assert client.post('/api/atlas', json={'query': 'logo', 'mode': 'live'}).status_code == 400
    assert client.post('/api/echo', json={'query': 'logo', 'mode': 'live'}).status_code == 400
    assert client.post('/api/canon', json={'mode': 'live'}).status_code == 400
    result = client.post('/api/experiments/relay', json={'mode': 'live'})
    assert result.status_code == 200 and result.json()['status'] == 'NOT_RUN'
    assert store.list('runs') == []
