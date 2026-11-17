"""Read-only bounded importers. Private sources never enter the public demo corpus."""
import hashlib
import json
import re
import shutil
import uuid
from pathlib import Path

from .models import EvidenceChunk, SourceDocument
from .store import ROOT, canonical

MAX_FILE = 24 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024

def safe_file(root, relative):
    root = Path(root).resolve(strict=True)
    value = Path(relative)
    if value.is_absolute() or '..' in value.parts:
        raise ValueError('Unsafe source path')
    path = root / value
    if any((root / Path(*value.parts[:n])).is_symlink() for n in range(1, len(value.parts)+1)):
        raise ValueError('Symlink source rejected')
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file() or resolved.stat().st_size > MAX_FILE:
        raise ValueError('Missing, oversized or unsafe source')
    return resolved

def hash_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def chunk_text(text, document_id, brand, snapshot, source_hash, max_chars=1400, origin='private'):
    """Keep entire sections/rule-exception paragraphs connected when split."""
    groups = re.split(r'(?m)(?=^#{1,6} )', text)
    chunks: list[EvidenceChunk] = []
    cursor = 0
    for group in groups:
        if not group.strip():
            cursor += len(group)
            continue
        title = group.splitlines()[0].lstrip('# ').strip()[:160]
        section_ids = []
        start = cursor
        while start < cursor + len(group):
            end = min(start + max_chars, cursor + len(group))
            if end < cursor + len(group):
                boundary = text.rfind('\n', start, end)
                if boundary > start + max_chars // 2:
                    end = boundary + 1
            body = text[start:end]
            key = f'{document_id}-{len(chunks)+1}'
            chunks.append(EvidenceChunk(id=key, document_id=document_id, brand=brand, snapshot=snapshot,
                                         title=title, text=body, section=title, source_hash=source_hash,
                                         data_origin=origin, status='unreviewed', authority='inferred', start=start, end=end))
            section_ids.append(key)
            start = end
        for chunk in chunks[-len(section_ids):]:
            chunk.links = [id for id in section_ids if id != chunk.id]
        cursor += len(group)
    return chunks

def import_document(root, relative, destination=None, brand='imported', snapshot='v1'):
    source = safe_file(root, relative)
    before = hash_file(source)
    suffix = source.suffix.lower()
    status = 'ready'
    if suffix in ('.txt','.md'):
        text = source.read_text(encoding='utf-8')
    elif suffix == '.pdf':
        from pypdf import PdfReader
        reader = PdfReader(source)
        if reader.is_encrypted:
            raise ValueError('Encrypted PDF is not supported')
        if len(reader.pages) > 600:
            raise ValueError('PDF page limit exceeded')
        text = '\n\n'.join(f'# Page {i+1}\n' + (p.extract_text() or '') for i,p in enumerate(reader.pages))
        if not any((p.extract_text() or '').strip() for p in reader.pages):
            status = 'IMAGE_ONLY_PDF_NO_OCR'
            text = ''
    else:
        raise ValueError('Only TXT, Markdown and text-layer PDF are supported')
    if len(text) > MAX_FILE:
        raise ValueError('Extracted text exceeds limit')
    document = SourceDocument(id=source.stem, brand=brand, version=snapshot, path=source.name, sha256=before,
                              data_origin='private', ingestion_status=status,
                              metadata={'chunker': 'sections-v1', 'max_chars':1400, 'ocr':False})
    chunks = chunk_text(text, source.stem, brand, snapshot, before)
    target = private_destination(destination)
    shutil.copyfile(source, target / source.name)
    (target/'document.json').write_text(canonical(document.model_dump()))
    (target/'chunks.json').write_text(canonical([c.model_dump() for c in chunks]))
    if hash_file(source) != before:
        raise ValueError('Source changed during import')
    return {'status':status, 'document':document.model_dump(), 'chunks':len(chunks), 'source_unchanged':True,
            'data_origin':'private', 'destination':str(target)}

def private_destination(destination=None):
    if (ROOT/'private').is_symlink():
        raise ValueError('Private destination cannot be a symlink')
    private_root = (ROOT/'private').resolve()
    target = Path(destination) if destination else private_root/'imports'/uuid.uuid4().hex
    if any(p.is_symlink() for p in [target,*target.parents] if p.is_relative_to(private_root)):
        raise ValueError('Private destination cannot traverse symlinks')
    if not target.resolve().is_relative_to(private_root):
        raise ValueError('Imported sources must remain under ignored private/')
    target.mkdir(parents=True, exist_ok=False)
    return target

def import_akella(akella_root, brand='stc', destination=None):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', brand):
        raise ValueError('Invalid brand identifier')
    root = Path(akella_root).resolve(strict=True)
    base = root / 'data/brands' / brand
    if not (base/'catalog.json').is_file():
        return {'status':'MISSING_PRIVATE_SOURCE', 'brand':brand, 'imported':False, 'verified':False}
    # Check every component including the brand folder; a corpus cannot escape the explicit root.
    safe_file(root, str((base/'catalog.json').relative_to(root)))
    catalog = json.loads(safe_file(base,'catalog.json').read_text())
    source = json.loads(safe_file(base,catalog['source']).read_text())
    records = json.loads(safe_file(base,catalog['records']).read_text())
    files = {'catalog.json':None, catalog['source']:None, catalog['records']:None}
    def add_file(name, expected):
        if name in files and files[name] is not None and files[name] != expected:
            raise ValueError('Conflicting source hashes')
        files[name] = expected
    if len(records) > 10000:
        raise ValueError('Record count limit exceeded')
    ids = {r['id'] for r in records}
    if len(ids) != len(records):
        raise ValueError('Duplicate evidence IDs')
    for record in records:
        required = {'id','kind','title','body','status','authority','polarity','scope','evidence','links'}
        if not required <= record.keys() or not record['scope'] or not record['evidence']:
            raise ValueError('Incomplete evidence contract')
        if record['status'] not in ('unreviewed','reviewed','superseded') or record['authority'] not in ('explicit','observed','inferred'):
            raise ValueError('Invalid review/authority')
        if record['kind'] not in ('rule','editorial','example','asset','measurement','composition') or record['polarity'] not in ('positive','negative','neutral','mixed','unknown'):
            raise ValueError('Invalid kind/polarity')
        if record['status'] == 'reviewed' and not record.get('review'):
            raise ValueError('Reviewed source requires review provenance')
        if not set(record['links']) <= ids:
            raise ValueError('Broken evidence link')
        for evidence in record['evidence']:
            if evidence.get('nodeId') not in source.get('nodeIds',[]):
                raise ValueError('Unknown source node')
            for key in ('file','image'):
                if key in evidence:
                    if not evidence.get(key+'Sha256'):
                        raise ValueError('Evidence hash required')
                    add_file(evidence[key], evidence[key+'Sha256'])
        if record['status']=='reviewed' and record['kind']=='example' and not any('image' in e for e in record['evidence']):
            raise ValueError('Reviewed example requires inspected image')
        if record['status']=='reviewed' and record['kind']=='asset' and not record.get('media'):
            raise ValueError('Reviewed asset requires media')
        for key in ('media','geometry'):
            if record.get(key):
                add_file(record[key]['file'], record[key]['sha256'])
    for resource in catalog.get('resources',[]):
        add_file(resource['file'], resource['sha256'])
    if catalog.get('authoring'):
        files[catalog['authoring']] = None
    before = {}
    total = 0
    for name, expected in files.items():
        path = safe_file(base,name)
        total += path.stat().st_size
        if total > MAX_TOTAL:
            raise ValueError('Import total limit exceeded')
        before[name] = hash_file(path)
        if expected and before[name] != expected:
            raise ValueError('Corrupted source hash')
    target = private_destination(destination)
    # Copy files only after ALL paths/hashes validated; preserve contract/provenance without promotion.
    for name in files:
        output = target/name
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(safe_file(base,name), output)
    after = {name: hash_file(safe_file(base,name)) for name in files}
    if before != after:
        raise ValueError('Source changed during read-only import')
    report = {'status':'IMPORTED_PRIVATE_SOURCE', 'brand':brand, 'imported':True, 'verified':True,
              'data_origin':'private', 'source_root':str(base), 'snapshot':catalog.get('snapshot'),
              'records':len(records), 'source_hashes_before':before, 'source_hashes_after':after,
              'source_unchanged':True, 'embedding_status':'NOT_INDEXED', 'destination':str(target)}
    (target/'import-report.json').write_text(canonical(report))
    return report
