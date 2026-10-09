"""Offline acceptance: build, extract, run public CLI, verify reproducibility."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import zipfile
import unittest

BASE = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(BASE))


def command(cwd, *args, expected=0):
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    proc = subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True, encoding='utf-8', env=env)
    if proc.returncode != expected:
        raise RuntimeError('Unexpected exit code for ' + args[0])
    return proc.stdout


def main():
    command(BASE, '-m', 'unittest', 'discover', '-s', 'tests', '-v')
    first = json.loads(command(BASE, 'release.py'))
    second = json.loads(command(BASE, 'release.py'))
    assert first == second
    contamination = BASE / 'synthetic-not-allowlisted.txt'
    with contamination.open('x') as f: f.write('synthetic')
    try:
        command(BASE, 'release.py', expected=1)
    finally:
        contamination.unlink()
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        with zipfile.ZipFile(BASE / 'dist' / first['archive']) as archive:
            archive.extractall(root)
        assert json.loads(command(root, 'release.py')) == first
        target = root / 'demo-work'; target.mkdir()
        command(root, 'starter.py', 'init', str(target))
        assert not list(target.iterdir())
        command(root, 'starter.py', 'init', str(target), '--apply', '--recovery')
        # A fresh process reads the initialized state before resuming the task.
        assert 'resume' in json.loads(command(root, 'starter.py', 'recover', str(target)))
        command(root, 'starter.py', 'demo', str(target), '--apply')
        result = json.loads((target / 'example/result.json').read_text())
        assert result == {'count': 3, 'total': 10}
        assert json.loads(command(root, 'starter.py', 'doctor', str(target)))['healthy']
        command(root, 'starter.py', 'recover', str(target))
        command(root, 'starter.py', 'init', str(target), '--apply', expected=2)
        (target / 'task.md').write_text('synthetic user edit')
        assert json.loads(command(root, 'starter.py', 'doctor', str(target)))['usable']
        command(root, 'starter.py', 'uninstall', str(target))
        assert (target / 'AGENTS.md').exists()
        command(root, 'starter.py', 'uninstall', str(target), '--apply')
        assert (target / 'task.md').read_text() == 'synthetic user edit'
        assert sorted(x.name for x in target.iterdir()) == ['.gitignore', 'private', 'task.md']
        # Fresh processes resume ordinary edits, but missing/corrupt state fails.
        edited = root / 'edited'; edited.mkdir()
        command(root, 'starter.py', 'init', str(edited), '--apply', '--recovery')
        for name in ['task.md', 'recovery/checkpoint.md', 'private/overlay.md']:
            (edited / name).write_text('synthetic progress')
        resumed = json.loads(command(root, 'starter.py', 'recover', str(edited)))
        assert resumed['usable'] and len(resumed['template_drift']) == 2
        assert 'resume' in resumed
        (edited / 'task.md').unlink()
        missing = json.loads(command(root, 'starter.py', 'recover', str(edited), expected=1))
        assert not missing['usable'] and 'resume' not in missing
        (edited / 'task.md').write_text('synthetic progress')
        statefile = edited / '.starter-state.json'
        original = statefile.read_bytes()
        statefile.write_text('{')
        command(root, 'starter.py', 'recover', str(edited), expected=2)
        statefile.write_bytes(original)
        command(root, 'starter.py', 'uninstall', str(edited), '--apply')
        assert all((edited / name).read_text() == 'synthetic progress' for name in ['task.md', 'recovery/checkpoint.md', 'private/overlay.md'])
        # Clean uninstall retains the user-owned private layer and its ignore rule.
        clean = root / 'clean'; clean.mkdir()
        command(root, 'starter.py', 'init', str(clean), '--apply')
        command(root, 'starter.py', 'rollback', str(clean), '--apply')
        assert sorted(x.name for x in clean.iterdir()) == ['.gitignore', 'private']
        # Export/import is the same core with user data, never a second product.
        minimal = root / 'minimal'; minimal.mkdir()
        command(root, 'starter.py', 'init', str(minimal), '--preset', 'minimal', '--apply')
        assert not (minimal / 'profile/style.md').exists()
        assert not (minimal / 'recovery').exists()
        (minimal / 'private/overlay.md').write_text('synthetic preference', encoding='utf-8')
        (minimal / 'private/profile.md').write_text('synthetic personal context', encoding='utf-8')
        (minimal / 'workspace/business.txt').write_text('EXCLUDED-BUSINESS', encoding='utf-8')
        exported = root / 'synthetic-profile.json'
        preview = command(root, 'starter.py', 'export-profile', str(minimal), '--output', str(exported))
        assert not exported.exists() and 'synthetic preference' not in preview
        command(root, 'starter.py', 'export-profile', str(minimal), '--output', str(exported), '--apply')
        assert 'EXCLUDED-BUSINESS' not in exported.read_text(encoding='utf-8')
        personal = root / 'personalized'; personal.mkdir()
        command(root, 'starter.py', 'init', str(personal), '--profile', str(exported))
        assert not list(personal.iterdir())
        command(root, 'starter.py', 'init', str(personal), '--profile', str(exported), '--apply')
        assert (personal / 'private/profile.md').read_text(encoding='utf-8') == 'synthetic personal context'
        assert json.loads(command(root, 'starter.py', 'doctor', str(personal)))['usable']
        command(root, 'starter.py', 'uninstall', str(personal), '--apply')
        assert (personal / 'private/profile.md').read_text(encoding='utf-8') == 'synthetic personal context'
        command(root, '-m', 'unittest', 'discover', '-s', 'tests', '-v')
    names = json.loads((BASE / 'release-allowlist.json').read_text(encoding='utf-8-sig'))
    forbidden = [os.environ.get('USERNAME', '').encode(), str(Path.home()).encode(), b'sk-proj-', b'BEGIN PRIVATE KEY']
    for name in names:
        data = (BASE / name).read_bytes()
        for term in forbidden[:2]:
            if len(term) > 3 and term.lower() in data.lower():
                raise RuntimeError('Local identity found in allowlisted content')
        # Credential markers in this test's own source are test definitions.
        if name != 'tests/acceptance.py':
            for term in forbidden[2:]:
                if term in data: raise RuntimeError('Credential marker found')
    report = {'platform': platform.system(), 'python': platform.python_version(), 'unit_tests': unittest.defaultTestLoader.discover(str(BASE / 'tests')).countTestCases(), 'extracted_unit_tests': 'same suite passed', 'edited_cross_process_recovery': 'passed', 'missing_corrupt_recovery_rejected': True, 'cli_lifecycle': 'passed', 'private_round_trip': 'passed', 'minimal_preset': 'passed', 'private_retained_on_exit': True, 'deterministic_zip': True, 'unlisted_file_rejected': True, 'privacy_scan': 'passed-supplementary', 'archive': first}
    output = BASE / '.qa'; output.mkdir(exist_ok=True)
    (output / 'acceptance.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
