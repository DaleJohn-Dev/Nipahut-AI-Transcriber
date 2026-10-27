"""Preserve installed distribution notices without copying binary dependencies."""
import importlib.metadata as metadata
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
dest = root / 'third-party'
dest.mkdir(exist_ok=True)
rows = []
for dist in sorted(metadata.distributions(), key=lambda d: d.metadata.get('Name', '').lower()):
    name = dist.metadata.get('Name', 'unknown')
    row = {'name': name, 'version': dist.version,
           'license': dist.metadata.get('License-Expression') or dist.metadata.get('License'),
           'project_urls': dist.metadata.get_all('Project-URL') or [], 'notices': []}
    for file in dist.files or []:
        parts = Path(str(file)).parts
        basename = Path(str(file)).name
        if any(part.endswith('.dist-info') for part in parts) and any(word in basename.upper() for word in ('LICENSE', 'COPYING', 'NOTICE', 'AUTHORS')):
            source = Path(dist.locate_file(file))
            if source.is_file() and source.stat().st_size < 1024**2:
                target = dest / name / basename
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(source.read_bytes())
                row['notices'].append(str(target.relative_to(root)))
    rows.append(row)
(dest / 'inventory.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'Preserved license metadata for {len(rows)} distributions.')
