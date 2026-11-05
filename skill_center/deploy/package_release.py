"""Package source, locked dependencies and the built frontend; never private data."""
from pathlib import Path
import hashlib
import json
import zipfile

root=Path(__file__).resolve().parents[1]
destination=root/'release'/'BioFlow_Skill_center_v1.2.zip'
destination.parent.mkdir(exist_ok=True)
excluded={'.venv','.ml-venv','node_modules','storage','test-results','backups','release','__pycache__','.pytest_cache','.git'}
with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as archive:
    for p in sorted(root.rglob('*')):
        if not p.is_file() or p.is_symlink(): continue
        relative=p.relative_to(root)
        if any(part in excluded for part in relative.parts) or p.suffix in {'.log','.pyc'} or p.name in {'source.zip','.env'}: continue
        archive.write(p,relative.as_posix())
print(json.dumps({'archive':str(destination),'size':destination.stat().st_size,'sha256':hashlib.sha256(destination.read_bytes()).hexdigest()}))
