"""Exact-allowlist deterministic ZIP builder; no third-party dependencies."""
import hashlib
import io
import json
from pathlib import Path
import zipfile
import starter as s

BASE = Path(__file__).absolute().parent


def build():
    names = json.loads((BASE / 'release-allowlist.json').read_text(encoding='utf-8-sig'))
    if len(names) != len(set(names)) or names != sorted(names):
        raise ValueError('Allowlist must be sorted and unique')
    ignored = {'.git', '.qa', 'dist', '__pycache__'}
    discovered = set()
    for p in BASE.rglob('*'):
        if any(part in ignored for part in p.relative_to(BASE).parts):
            continue
        s.reject_link(p)
        if p.is_file(): discovered.add(p.relative_to(BASE).as_posix())
    discovered.discard('release-manifest.json')
    if discovered != set(names):
        raise ValueError('Repository differs from exact publication allowlist')
    contents = {name: s.child(BASE, name).read_bytes() for name in names}
    if contents['VERSION'].decode().strip() != s.VERSION:
        raise ValueError('Version mismatch')
    manifest = {'version': s.VERSION, 'source': 'generic-core-and-adapted-collaboration-methods', 'license': 'MIT', 'files': {name: {'sha256': s.digest(data), 'bytes': len(data)} for name, data in contents.items()}}
    embedded = BASE / 'release-manifest.json'
    if embedded.exists() and embedded.read_bytes() != s.encoded(manifest):
        raise ValueError('Embedded manifest mismatch')
    contents['release-manifest.json'] = s.encoded(manifest)
    out = BASE / 'dist'; s.reject_link(out); out.mkdir(exist_ok=True)
    archive = out / ('harness-starter-' + s.VERSION + '.zip')
    s.reject_link(archive)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_STORED) as z:
        for name, data in sorted(contents.items()):
            info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.create_system = 3; info.external_attr = 0o100644 << 16
            z.writestr(info, data)
    data = buffer.getvalue()
    if archive.exists():
        if archive.read_bytes() != data:
            raise ValueError('Release already exists with different bytes; bump version')
    else:
        with archive.open('xb') as stream:
            stream.write(data)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None or set(z.namelist()) != set(contents):
            raise ValueError('ZIP verification failed')
        for name, data in contents.items():
            if z.read(name) != data: raise ValueError('ZIP content mismatch')
    manifest['archive'] = {'name': archive.name, 'sha256': s.digest(archive.read_bytes())}
    destination = out / 'release-manifest.json'; s.reject_link(destination)
    destination.write_bytes(s.encoded(manifest))
    print(json.dumps({'archive': archive.name, 'sha256': manifest['archive']['sha256'], 'files': len(names)}))
    return archive


if __name__ == '__main__':
    build()
