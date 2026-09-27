import importlib.util
import pathlib
import unittest

import os
import tempfile

# Keep fixture writes in the agent scratch workspace, never system temp.
SCRATCH = pathlib.Path(os.environ.get('HERMES_HOME', pathlib.Path.home() / '.hermes')) / 'cache' / 'scratch'
SCRATCH.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(SCRATCH)
ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/robot_icon.py'

def module():
    spec = importlib.util.spec_from_file_location('robot_icon', SCRIPT)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

class Tests(unittest.TestCase):
    def test_recolor_preserves_everything_except_accent_tokens(self):
        self.assertTrue(SCRIPT.exists(), 'recolor implementation missing')
        m = module()
        original = (ROOT / 'assets/robot_icon.svg').read_text()
        colored = m.recolor(original, '#cc3355')
        import re
        accents = ['#6a8dff', '#3b5bdb', '#8fe3ff', '#22a7f0', '#0b6fb8']
        normalized = original
        for c in accents:
            normalized = normalized.replace(c, 'ACCENT')
        actual = colored
        for c in m.palette('#cc3355').values():
            actual = actual.replace(c, 'ACCENT')
        self.assertEqual(normalized, actual)
        self.assertIn('stop-color="#ffffff"', colored)
        self.assertIn('stop-color="#e6ecff"', colored)
        self.assertNotEqual(original, colored)

    def test_invalid_color(self):
        for value in ('red', '#123', '#1234567', ' #abcdef', '#abcdeg'):
            with self.assertRaises(ValueError):
                module().palette(value)

    def test_render(self):
        import tempfile, struct
        m = module()
        self.assertTrue(hasattr(m, 'render'), 'render implementation missing')
        with tempfile.TemporaryDirectory() as d:
            m.render('#CB003D', pathlib.Path(d))
            png = (pathlib.Path(d) / 'robot.png').read_bytes()
            self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
            self.assertEqual(struct.unpack('>II', png[16:24]), (1024, 1024))
            self.assertIn('#cb003d', (pathlib.Path(d) / 'robot.svg').read_text())

    def test_apply_fixture_and_rollback(self):
        import tempfile, json, struct, hashlib, plistlib, shutil, sys
        from unittest.mock import patch
        if sys.platform != 'darwin':
            self.skipTest('macOS installation test')
        m = module()
        self.assertTrue(hasattr(m, 'apply'), 'transactional apply missing')
        with tempfile.TemporaryDirectory() as d:
            base = pathlib.Path(d)
            app = base / 'Fixture.app'
            res = app / 'Contents/Resources'
            res.mkdir(parents=True)
            exe = app / 'Contents/MacOS'
            exe.mkdir()
            shutil.copyfile('/usr/bin/true', exe / 'fixture')
            (exe / 'fixture').chmod(0o755)
            header = {'files': {'dist': {'files': {'apple-touch-icon.png': {'size': 3, 'offset': '0', 'integrity': {'algorithm': 'SHA256', 'hash': hashlib.sha256(b'old').hexdigest(), 'blockSize': 4194304, 'blocks': [hashlib.sha256(b'old').hexdigest()]}}}}, 'native.bin': {'size': 4, 'unpacked': True}}}
            raw = json.dumps(header, separators=(',', ':')).encode()
            pad = b'\0' * ((-len(raw)) % 4)
            (res / 'app.asar').write_bytes(struct.pack('<4I', 4, 8 + len(raw) + len(pad), 4 + len(raw) + len(pad), len(raw)) + raw + pad + b'old')
            unpacked = res / 'app.asar.unpacked'
            unpacked.mkdir()
            (unpacked / 'native.bin').write_bytes(b'keep')
            info = {'CFBundleIdentifier': 'fixture', 'CFBundleExecutable': 'fixture', 'CFBundlePackageType': 'APPL', 'CFBundleIconFile': 'icon.icns', 'ElectronAsarIntegrity': {'Resources/app.asar': {'algorithm': 'SHA256', 'hash': hashlib.sha256(raw).hexdigest()}}}
            (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
            (res / 'icon.icns').write_bytes(b'old')
            m.run('codesign', '--force', '--sign', '-', app)
            original = (res / 'app.asar').read_bytes()
            backup = m.apply(app, '#CB003D', base / 'state')
            self.assertEqual((backup / 'Contents/Resources/app.asar').read_bytes(), original)
            patched, body = m.read_asar(res / 'app.asar')
            self.assertTrue(patched['files']['native.bin']['unpacked'])
            self.assertEqual((unpacked / 'native.bin').read_bytes(), b'keep')
            self.assertEqual((res / 'icon.icns').read_bytes()[:4], b'icns')
            m.run('codesign', '--verify', '--deep', '--strict', app)
            after = (res / 'app.asar').read_bytes()
            original_verify = m.verify_app
            calls = []
            def fail_after_install(target):
                calls.append(target)
                if pathlib.Path(target).resolve() == app.resolve():
                    raise ValueError('injected verification failure')
                return original_verify(target)
            with patch.object(m, 'verify_app', side_effect=fail_after_install):
                with self.assertRaisesRegex(ValueError, 'injected'):
                    m.apply(app, '#123456', base / 'state')
            self.assertEqual((res / 'app.asar').read_bytes(), after)
            m.run('codesign', '--verify', '--deep', '--strict', app)

    def test_cli_requires_explicit_target(self):
        import subprocess, sys
        proc = subprocess.run([sys.executable, str(SCRIPT), '--apply', '--accent', '#CB003D'], capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0, 'CLI must reject missing explicit app')
        self.assertIn('--app', proc.stderr)

if __name__ == '__main__':
    unittest.main()
