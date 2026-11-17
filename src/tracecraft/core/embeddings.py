"""Explicit preparation; inference has no download path and no lexical fallback."""
import hashlib
import importlib.util
import json
import os
import threading
import urllib.request
from pathlib import Path

from .store import ROOT, canonical, digest

# Tokenization is serial under the encoder lock; disable fork-unsafe Rayon workers.
os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')

MODEL_CONFIG = json.loads((ROOT / 'configs/embedding.json').read_text())
MODEL_DIR = ROOT / 'runtime/models/e5-small'

class ModelUnavailable(RuntimeError):
    pass

def file_sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def prepare_model(destination=MODEL_DIR):
    """Only this explicitly invoked command contacts the model host."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name in MODEL_CONFIG['files']:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://huggingface.co/{MODEL_CONFIG['model']}/resolve/{MODEL_CONFIG['revision']}/{name}"
        temporary = target.with_suffix(target.suffix + '.partial')
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open('wb') as out:
            total = 0
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > 1024 * 1024 * 1024:
                    raise ValueError('Model file exceeds 1 GiB limit')
                out.write(block)
        os.replace(temporary, target)
        hashes[name] = file_sha(target)
    manifest = {'config': MODEL_CONFIG, 'hashes': hashes}
    (destination / 'manifest.json').write_text(canonical(manifest))
    return {'status': 'prepared', 'model': MODEL_CONFIG['model'], 'revision': MODEL_CONFIG['revision'], 'hashes': hashes}

class Encoder:
    def __init__(self, directory=MODEL_DIR):
        self.directory = Path(directory)
        self.session = None
        self.tokenizer = None
        self.lock = threading.Lock()
        self.fingerprint = digest(MODEL_CONFIG)
        self.model_id = f"{MODEL_CONFIG['model']}@{MODEL_CONFIG['revision']}"
        self.calls = 0

    def status(self):
        missing = [p for p in ('numpy', 'onnxruntime', 'tokenizers') if importlib.util.find_spec(p) is None]
        if missing:
            return {'status': 'MODEL_NOT_PREPARED', 'reason': 'Optional dependencies missing: ' + ', '.join(missing)}
        if not (self.directory / 'manifest.json').exists():
            return {'status': 'MODEL_NOT_PREPARED', 'reason': 'Run make models explicitly; no automatic download.'}
        return {'status': 'ready', 'model': self.model_id, 'provider': 'CPUExecutionProvider'}

    def _load(self):
        status = self.status()
        if status['status'] != 'ready':
            raise ModelUnavailable(status['reason'])
        if self.session is not None:
            return
        import onnxruntime as ort
        from tokenizers import Tokenizer
        manifest = json.loads((self.directory / 'manifest.json').read_text())
        if manifest['config'] != MODEL_CONFIG:
            raise ModelUnavailable('Model revision/config changed: prepare model again')
        for name in MODEL_CONFIG['files']:
            if file_sha(self.directory / name) != manifest['hashes'].get(name):
                raise ModelUnavailable('Model file integrity mismatch')
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        self.session = ort.InferenceSession(str(self.directory / 'onnx/model.onnx'), sess_options=options,
                                            providers=['CPUExecutionProvider'])
        self.tokenizer = Tokenizer.from_file(str(self.directory / 'tokenizer.json'))
        self.tokenizer.enable_padding(pad_id=1, pad_token='<pad>')

    def encode(self, texts: list[str], kind='query') -> list[list[float]]:
        import numpy as np
        with self.lock:
            self._load()
            assert self.tokenizer is not None and self.session is not None
            encoded = self.tokenizer.encode_batch([MODEL_CONFIG['prefixes'][kind] + text for text in texts])
            if any(len(item.ids) > MODEL_CONFIG['max_tokens'] for item in encoded):
                raise ValueError('Embedding input exceeds 512 tokens; split source explicitly')
            arrays = {'input_ids': np.asarray([e.ids for e in encoded], dtype=np.int64),
                      'attention_mask': np.asarray([e.attention_mask for e in encoded], dtype=np.int64),
                      'token_type_ids': np.asarray([e.type_ids for e in encoded], dtype=np.int64)}
            inputs = {i.name: arrays[i.name] for i in self.session.get_inputs()}
            output = self.session.run(None, inputs)[0]
            mask = arrays['attention_mask'][..., None]
            vectors = (output * mask).sum(axis=1) / mask.sum(axis=1)
            vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
            if not np.isfinite(vectors).all():
                raise ValueError('Nonfinite embedding')
            self.calls += 1
            return vectors.tolist()

def cosine(a, b):
    if len(a) != len(b):
        raise ValueError('Incompatible embedding dimensions')
    return sum(x * y for x, y in zip(a, b))
