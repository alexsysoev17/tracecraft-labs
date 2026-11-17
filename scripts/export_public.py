"""Prepare a review copy, never publish or push it."""
import json
import shutil
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from tracecraft.core.reports import privacy_check  # noqa: E402

DIRECTORIES=('src','web','docs','datasets/public-demo','reports/public','tests','examples','configs','scripts','.github')
FILES=('README.md','AGENTS.md','PLAN.md','CONTRIBUTING.md','SECURITY.md','LIMITATIONS.md','THIRD_PARTY_NOTICES.md',
       'Makefile','pyproject.toml','.gitignore','RUNS_MANIFEST.json','requirements.txt','requirements-dev.txt',
       'requirements-local.txt','requirements-fixture.lock','requirements-local.lock')

def export(destination):
    result=privacy_check()
    if result['status']!='PASS':
        raise ValueError(result)
    # Check all selected sources before creating any output. Never follow an
    # allowlisted-looking symlink into an excluded tree or an external directory.
    for name in (*DIRECTORIES,*FILES):
        source=ROOT/name
        parts=Path(name).parts
        if any(ROOT.joinpath(*parts[:i]).is_symlink() for i in range(1,len(parts)+1)):
            raise ValueError('Public export rejected: symlink in selected source ancestors')
        paths=[source]+(list(source.rglob('*')) if source.is_dir() and not source.is_symlink() else [])
        if any(p.is_symlink() for p in paths):
            raise ValueError('Public export rejected: symlink in selected sources')
    destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=False)
    for name in DIRECTORIES:
        source=ROOT/name
        if source.exists():
            shutil.copytree(source,destination/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for name in FILES:
        if (ROOT/name).is_file():
            shutil.copyfile(ROOT/name,destination/name)
    assert not (destination/'runtime').exists() and not (destination/'private').exists()
    print(json.dumps({'status':'PREPARED_FOR_REVIEW','files':sum(p.is_file() for p in destination.rglob('*')),
                      'published':False,'audit':result},indent=2))

if __name__=='__main__':
    export(sys.argv[1] if len(sys.argv)>1 else ROOT/'dist/public-review')
