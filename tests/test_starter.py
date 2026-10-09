import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import starter as s


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.target = self.root / 'empty'
        self.target.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def call(self, command, apply=False, recovery=False, **kwargs):
        return s.run(argparse.Namespace(command=command, target=str(self.target), apply=apply, recovery=recovery, **kwargs))

    def init(self, recovery=False):
        return self.call('init', True, recovery)

    def test_full_lifecycle(self):
        self.call('init')
        self.assertEqual(list(self.target.iterdir()), [])
        self.init(True)
        self.call('demo')
        self.assertFalse((self.target / 'example').exists())
        self.call('demo', True)
        self.assertEqual(json.loads((self.target / 'example/result.json').read_text()), {'count': 3, 'total': 10})
        self.assertTrue(self.call('doctor')['healthy'])
        self.assertIn('resume', self.call('recover'))
        self.call('uninstall')
        self.assertTrue((self.target / s.STATE).exists())
        self.call('rollback', True)
        self.assertEqual({p.relative_to(self.target).as_posix() for p in self.target.rglob('*') if p.is_file()}, {'.gitignore', 'private/overlay.md'})

    def test_preserve_modified_and_unmanaged(self):
        self.init()
        (self.target / 'task.md').write_text('user content')
        (self.target / 'my-work.txt').write_text('unmanaged')
        self.assertTrue(self.call('doctor')['healthy'])
        report = self.call('uninstall', True)
        self.assertEqual(set(report['preserve_modified']), {'task.md', '.gitignore'})
        self.assertEqual((self.target / 'task.md').read_text(), 'user content')
        self.assertEqual((self.target / 'my-work.txt').read_text(), 'unmanaged')

    def test_private_edits_keep_ignore(self):
        self.init()
        (self.target / 'private/overlay.md').write_text('synthetic preference')
        result = self.call('uninstall', True)
        self.assertIn('.gitignore', result['preserve_modified'])
        self.assertTrue((self.target / '.gitignore').exists())
        self.assertEqual((self.target / 'private/overlay.md').read_text(), 'synthetic preference')

    def test_edited_task_recovers(self):
        self.init(True)
        for name in ['task.md', 'recovery/checkpoint.md', 'private/overlay.md']:
            (self.target / name).write_text('synthetic progress')
        report = self.call('recover')
        self.assertTrue(report['healthy'])
        self.assertTrue(report['usable'])
        self.assertEqual(set(report['template_drift']), {'task.md', 'recovery/checkpoint.md'})
        self.assertIn('resume', report)
        self.call('demo', True)

    def test_nonempty_and_repeat_init(self):
        self.init()
        before = (self.target / s.STATE).read_bytes()
        with self.assertRaises(s.Refusal): self.init()
        self.assertEqual((self.target / s.STATE).read_bytes(), before)

    def test_missing_file(self):
        self.init()
        (self.target / 'task.md').unlink()
        self.assertEqual(self.call('doctor')['files']['task.md'], 'missing')
        self.assertFalse(self.call('recover')['usable'])
        self.assertNotIn('resume', self.call('recover'))
        with self.assertRaises(s.Refusal): self.call('demo', True)

    def test_demo_no_overwrite(self):
        self.init()
        self.call('demo', True)
        with self.assertRaises(s.Refusal): self.call('demo', True)

    def test_path_attacks(self):
        for name in ['../escape', '/root', 'C:/escape', 'a\\b', 'a/../b', './a', 'a//b']:
            with self.subTest(name=name), self.assertRaises(s.Refusal): s.child(self.target, name)

    def test_poisoned_state(self):
        self.init()
        statefile = self.target / s.STATE
        baseline = json.loads(statefile.read_text())
        for key in ['../outside', 'unmanaged.txt', 'C:/outside']:
            data = json.loads(json.dumps(baseline))
            data['files'][key] = '0' * 64
            statefile.write_text(json.dumps(data))
            with self.assertRaises(s.Refusal): self.call('uninstall', True)
            self.assertTrue((self.target / 'AGENTS.md').exists())

    def test_hash_tamper(self):
        self.init()
        statefile = self.target / s.STATE
        data = json.loads(statefile.read_text())
        data['files']['task.md'] = '0' * 64
        statefile.write_text(json.dumps(data))
        with self.assertRaises(s.Refusal): self.call('uninstall', True)

    def test_unknown_version(self):
        self.init()
        f = self.target / s.STATE
        data = json.loads(f.read_text()); data['version'] = '999'
        f.write_text(json.dumps(data))
        with self.assertRaises(s.Refusal): self.call('doctor')

    def test_hardlink_rejected(self):
        original = self.root / 'outside.txt'; original.write_text('safe')
        os.link(original, self.target / 'linked.txt')
        with self.assertRaises(s.Refusal): self.call('init', True)
        self.assertEqual(original.read_text(), 'safe')

    @unittest.skipUnless(os.name == 'nt', 'Windows junction test')
    def test_junction_rejected(self):
        outside = self.root / 'outside'; outside.mkdir()
        link = self.target / 'junction'
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)], capture_output=True)
        self.assertEqual(result.returncode, 0)
        try:
            with self.assertRaises(s.Refusal): self.call('init', True)
            with self.assertRaises(s.Refusal): s.root_path(link / 'nested')
        finally:
            link.rmdir()

    def test_partial_init_rolls_back(self):
        real_open = Path.open
        def fail(path, *args, **kwargs):
            if path.name == 'task.md' and args and args[0] == 'xb':
                raise OSError('simulated write failure')
            return real_open(path, *args, **kwargs)
        with patch.object(Path, 'open', fail), self.assertRaises(OSError): self.init()
        self.assertEqual(list(self.target.iterdir()), [])

    def test_corrupt_state(self):
        self.init(); (self.target / s.STATE).write_text('{')
        with self.assertRaises(ValueError): self.call('doctor')

    def test_runtime_root_refused(self):
        with self.assertRaises(s.Refusal): s.root_path(self.target.anchor)

    def profile(self, files=None):
        path = self.root / 'profile.json'
        path.write_text(json.dumps({'schema': s.PROFILE_SCHEMA, 'version': 1,
            'files': files or {'private/overlay.md': 'synthetic preference', 'private/profile.md': 'synthetic profile'}}), encoding='utf-8')
        return str(path)

    def test_presets(self):
        result = self.call('init', preset='minimal')
        self.assertNotIn('profile/style.md', result['files'])
        self.assertNotIn('recovery/checkpoint.md', result['files'])
        result = self.call('init')
        self.assertTrue(set(s.RECOMMENDED + s.RECOVERY).issubset(result['files']))

    def test_profile_round_trip(self):
        source = self.profile()
        self.call('init', profile=source)
        self.assertEqual(list(self.target.iterdir()), [])
        self.call('init', True, profile=source)
        (self.target / 'workspace/business.txt').write_text('BUSINESS-SECRET')
        output = self.root / 'export.json'
        preview = self.call('export-profile', output=str(output))
        self.assertFalse(output.exists())
        self.assertNotIn('synthetic preference', json.dumps(preview))
        self.call('export-profile', True, output=str(output))
        self.assertEqual(s.read_profile(source), s.read_profile(output))
        self.assertNotIn('BUSINESS-SECRET', output.read_text())
        self.call('uninstall', True)
        self.assertEqual((self.target / 'private/profile.md').read_text(), 'synthetic profile')
        self.assertTrue((self.target / '.gitignore').exists())

    def test_profile_validation(self):
        path = Path(self.profile())
        baseline = json.loads(path.read_text())
        invalid = [[], {'schema': 'bad', 'version': 1, 'files': {}},
            {**baseline, 'version': True}, {**baseline, 'extra': 1},
            {**baseline, 'files': {'private/overlay.md': 'ok', '../escape': 'bad'}},
            {**baseline, 'files': {'private/overlay.md': 2}},
            {**baseline, 'files': {'private/overlay.md': 'x' * (s.MAX_TEXT_BYTES + 1)}},
            {**baseline, 'files': {'private/overlay.md': 'bad\x00text'}}]
        for data in invalid:
            path.write_text(json.dumps(data))
            with self.assertRaises((s.Refusal, ValueError)):
                self.call('init', True, profile=str(path))
            self.assertEqual(list(self.target.iterdir()), [])
        path.write_text('{"schema":1,"schema":2}')
        with self.assertRaises(s.Refusal): s.read_profile(path)

    def test_profile_missing_and_tamper(self):
        self.call('init', True, profile=self.profile())
        (self.target / 'private/profile.md').unlink()
        self.assertFalse(self.call('doctor')['healthy'])
        self.assertNotIn('resume', self.call('recover'))
        f = self.target / s.STATE
        data = json.loads(f.read_text())
        data['files']['private/overlay.md'] = s.digest((self.target / 'private/overlay.md').read_bytes())
        f.write_text(json.dumps(data))
        with self.assertRaises(s.Refusal): self.call('uninstall', True)

    def test_export_refusals(self):
        self.init()
        output = self.root / 'exists.json'; output.write_text('keep')
        for path in [output, self.target / 'new.json', self.target / s.STATE]:
            with self.assertRaises(s.Refusal): self.call('export-profile', True, output=str(path))
        self.assertEqual(output.read_text(), 'keep')
        (self.target / 'private/overlay.md').write_text('x' * (s.MAX_TEXT_BYTES + 1))
        with self.assertRaises(s.Refusal): self.call('export-profile', True, output=str(self.root / 'new.json'))

    def test_profile_partial_init_rolls_back(self):
        real_open = Path.open
        def fail(path, *args, **kwargs):
            if path.name == 'profile.md' and args and args[0] == 'xb':
                raise OSError('simulated')
            return real_open(path, *args, **kwargs)
        profile = self.profile()
        with patch.object(Path, 'open', fail), self.assertRaises(OSError):
            self.call('init', True, profile=profile)
        self.assertEqual(list(self.target.iterdir()), [])

    def test_export_failed_write_rolls_back(self):
        self.init()
        output = self.root / 'failed.json'
        real_open = Path.open
        class FailingStream:
            def __enter__(self): return self
            def __exit__(self, *args): self.stream.close()
            def write(self, data):
                self.stream.write(data[:5]); raise OSError('simulated')
        def fail(path, *args, **kwargs):
            stream = real_open(path, *args, **kwargs)
            if path == output and args and args[0] == 'xb':
                wrapper = FailingStream(); wrapper.stream = stream; return wrapper
            return stream
        with patch.object(Path, 'open', fail), self.assertRaises(OSError):
            self.call('export-profile', True, output=str(output))
        self.assertFalse(output.exists())

    def test_old_release_state_refused_without_changes(self):
        self.init()
        state = self.target / s.STATE
        old = {'version': '0.1.0-rc.2', 'modules': [], 'files': {}}
        state.write_text(json.dumps(old))
        before = {p.relative_to(self.target).as_posix(): p.read_bytes() for p in self.target.rglob('*') if p.is_file()}
        with self.assertRaisesRegex(s.Refusal, 'original release'):
            self.call('uninstall', True)
        self.assertEqual(before, {p.relative_to(self.target).as_posix(): p.read_bytes() for p in self.target.rglob('*') if p.is_file()})

    def test_profile_input_hardlink_refused(self):
        profile = Path(self.profile())
        alias = self.root / 'alias.json'; os.link(profile, alias)
        with self.assertRaises(s.Refusal): self.call('init', True, profile=str(alias))
        self.assertEqual(list(self.target.iterdir()), [])

    def test_imported_template_bytes_still_preserved(self):
        text = (s.BASE / 'templates/private/overlay.md').read_text(encoding='utf-8')
        self.call('init', True, profile=self.profile({'private/overlay.md': text}))
        self.call('uninstall', True)
        self.assertTrue((self.target / 'private/overlay.md').exists())

    def test_cli_never_echoes_profile_text(self):
        result = subprocess.run([os.sys.executable, '-X', 'utf8', '-B', str(s.BASE / 'starter.py'),
            'init', str(self.target), '--profile', self.profile()], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0)
        self.assertNotIn('synthetic preference', result.stdout + result.stderr)
        self.assertEqual(list(self.target.iterdir()), [])

    def test_reserved_paths_refused_before_filesystem_access(self):
        names = ['CON', 'NUL', 'AUX.json', 'COM1.txt', 'LPT9.log', 'COM¹.txt',
                 'folder/NUL.txt', 'file.', 'file ', 'folder /file',
                 'file:stream', 'C:relative', 'bad\x01name', 'bad\x7fname',
                 '//./CON', '//?/C:/file', '//./pipe/example', '/??/C:/file']
        names += [name.replace('/', chr(92)) for name in names if '/' in name]
        for name in names:
            for function in (s.file_path, s.root_path, s.read_profile):
                with self.subTest(name=name, function=function.__name__):
                    with patch.object(Path, 'lstat', side_effect=AssertionError('filesystem accessed')):
                        with self.assertRaises(s.Refusal): function(name)
            with patch.object(Path, 'lstat', side_effect=AssertionError('filesystem accessed')):
                with self.assertRaises(s.Refusal): s.child(self.target, name)

    def test_portable_path_text_acceptance(self):
        for name in ['C:/normal/file.json', 'D:/个人/配置.json', '/tmp/config.json',
                     'relative/file.json', './relative', '../sibling', '.gitignore']:
            s.validate_path_text(name)

    def test_nonregular_json_refused_without_read(self):
        from types import SimpleNamespace
        import stat
        path = Path(self.profile())
        with patch.object(Path, 'stat', return_value=SimpleNamespace(st_mode=stat.S_IFIFO, st_size=0)):
            with patch.object(Path, 'read_bytes', side_effect=AssertionError('content read')):
                with self.assertRaises(s.Refusal): s.load_json(path)

    def test_directory_profile_refused_without_read(self):
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('content read')):
            with self.assertRaises(s.Refusal): s.read_profile(self.target)


if __name__ == '__main__':
    unittest.main()
