#!/usr/bin/env python3
"""Portable robot recoloring; explicit transactional macOS installation."""
import re
import pathlib
import subprocess
import struct
import os
import sys
import json
import hashlib
import plistlib
import shutil
import tempfile
import datetime
import uuid
import argparse

ROOT = pathlib.Path(__file__).resolve().parents[1]


def run(*args):
    return subprocess.run([str(a) for a in args], check=True, capture_output=True)


def render(accent, output):
    svg = recolor((ROOT / 'assets/robot_icon.svg').read_text(), accent)
    output = pathlib.Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'robot.svg').write_text(svg)
    run('rsvg-convert', '-w', '1024', '-h', '1024', output / 'robot.svg', '-o', output / 'robot.png')
    data = (output / 'robot.png').read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n' or struct.unpack('>II', data[16:24]) != (1024, 1024):
        raise ValueError('Renderer did not produce a 1024px PNG')
    return output


def palette(accent):
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', accent):
        raise ValueError('Accent must be exactly #RRGGBB')
    rgb = [int(accent[i:i + 2], 16) for i in (1, 3, 5)]
    def shade(t):
        return '#' + ''.join(f'{round(v + (255-v)*t) if t >= 0 else round(v*(1+t)):02x}' for v in rgb)
    return dict(zip(('#6a8dff', '#3b5bdb', '#8fe3ff', '#22a7f0', '#0b6fb8'), (shade(.25), shade(-.15), shade(.55), accent.lower(), shade(-.35))))


def recolor(svg, accent):
    colors = palette(accent)
    return re.sub('|'.join(colors), lambda m: colors[m[0]], svg)


def read_asar(path):
    data = pathlib.Path(path).read_bytes()
    if len(data) < 16:
        raise ValueError('Truncated archive')
    first, size, payload, length = struct.unpack('<4I', data[:16])
    if first != 4 or payload != size - 4 or length > size - 8 or size + 8 > len(data):
        raise ValueError('Unsupported archive header')
    return json.loads(data[16:16 + length]), data[8 + size:]


def header_hash(path):
    data = pathlib.Path(path).read_bytes()
    length = struct.unpack('<I', data[12:16])[0]
    return hashlib.sha256(data[16:16 + length]).hexdigest()


def entries(tree, prefix=''):
    for name, node in tree['files'].items():
        if name in ('.', '..') or '/' in name or '\\' in name:
            raise ValueError('Unsafe archive entry')
        path = prefix + name
        if 'files' in node:
            yield from entries(node, path + '/')
        else:
            yield path, node


def patch_asar(path, png):
    header, original_body = read_asar(path)
    body = bytearray(original_body)
    changed = []
    for name, entry in entries(header):
        if name not in ('dist/apple-touch-icon.png', 'public/apple-touch-icon.png'):
            continue
        if 'link' in entry:
            raise ValueError('Icon entry cannot be a link')
        if entry.get('unpacked'):
            target = pathlib.Path(str(path) + '.unpacked') / name
            if not target.is_file() or target.is_symlink():
                raise ValueError('Missing or symlinked unpacked icon')
            target.write_bytes(png)
        else:
            entry['offset'] = str(len(body))
            body.extend(png)
        entry['size'] = len(png)
        old = entry.get('integrity', {})
        if old.get('algorithm', 'SHA256') != 'SHA256':
            raise ValueError('Unsupported archive integrity algorithm')
        block = old.get('blockSize', 4194304)
        if not isinstance(block, int) or block <= 0:
            raise ValueError('Invalid integrity block size')
        entry['integrity'] = {'algorithm': 'SHA256', 'hash': hashlib.sha256(png).hexdigest(), 'blockSize': block, 'blocks': [hashlib.sha256(png[i:i + block]).hexdigest() for i in range(0, len(png), block)]}
        changed.append(name)
    if not changed:
        raise ValueError('No supported runtime icon paths in archive; target left untouched')
    raw = json.dumps(header, separators=(',', ':'), ensure_ascii=False).encode()
    pad = b'\0' * (-len(raw) % 4)
    path.write_bytes(struct.pack('<4I', 4, len(raw) + len(pad) + 8, len(raw) + len(pad) + 4, len(raw)) + raw + pad + body)
    actual, new_body = read_asar(path)
    for name, entry in entries(actual):
        if name in changed:
            data = (pathlib.Path(str(path) + '.unpacked') / name).read_bytes() if entry.get('unpacked') else new_body[int(entry['offset']):int(entry['offset']) + entry['size']]
            if data != png:
                raise ValueError('Archive icon verification failed')
    return changed


def verify_app(app):
    info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    for name, record in info.get('ElectronAsarIntegrity', {}).items():
        p = pathlib.PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or record.get('algorithm') != 'SHA256':
            raise ValueError('Unsupported bundle integrity entry')
        if header_hash(app / 'Contents' / name) != record['hash']:
            raise ValueError('Bundle archive header hash mismatch')
    run('codesign', '--verify', '--deep', '--strict', app)


def apply(app, accent, state):
    palette(accent)
    if sys.platform != 'darwin':
        raise ValueError('Installation is macOS-only; use --render-only on other systems')
    supplied = pathlib.Path(app).expanduser()
    if supplied.is_symlink():
        raise ValueError('Choose a real app bundle, not a symlink')
    app = supplied.resolve()
    state = pathlib.Path(state).expanduser().resolve()
    if app.suffix != '.app' or not (app / 'Contents/Info.plist').is_file():
        raise ValueError('Explicit --app must identify one existing .app bundle')
    if state == app or app in state.parents:
        raise ValueError('State and backups must be outside the app')
    for tool in ('rsvg-convert', 'iconutil', 'codesign', 'ditto'):
        if not shutil.which(tool):
            raise ValueError('Missing dependency: ' + tool)
    state.mkdir(parents=True, exist_ok=True)
    lock = state / 'apply.lock'
    try:
        lock.mkdir()
    except FileExistsError:
        raise ValueError('Another apply or interrupted transaction exists; inspect apply.lock first')
    backup = None
    parked = None
    installed = False
    try:
        size = sum(p.stat().st_size for p in app.rglob('*') if p.is_file() and not p.is_symlink())
        if shutil.disk_usage(app.parent).free < size * 3 or shutil.disk_usage(state).free < size * 2:
            raise ValueError('Insufficient free space for staging and backup')
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ') + '-' + uuid.uuid4().hex[:8]
        backup = state / 'backups' / stamp / app.name
        backup.parent.mkdir(parents=True)
        run('ditto', app, backup)
        with tempfile.TemporaryDirectory(prefix='.robot-stage-', dir=app.parent) as temp:
            stage = pathlib.Path(temp) / app.name
            run('ditto', app, stage)
            output = render(accent, pathlib.Path(temp) / 'render')
            iconset = pathlib.Path(temp) / 'robot.iconset'
            iconset.mkdir()
            for size in (16, 32, 128, 256, 512):
                for scale in (1, 2):
                    name = f'icon_{size}x{size}' + ('@2x' if scale == 2 else '') + '.png'
                    run('rsvg-convert', '-w', size * scale, '-h', size * scale, output / 'robot.svg', '-o', iconset / name)
            info_path = stage / 'Contents/Info.plist'
            info = plistlib.loads(info_path.read_bytes())
            icon = info.get('CFBundleIconFile', '')
            if not icon or pathlib.Path(icon).name != icon:
                raise ValueError('Unsupported bundle icon name')
            if not icon.endswith('.icns'):
                icon += '.icns'
            resources = stage / 'Contents/Resources'
            for target in (resources / icon, resources / 'app.asar', info_path):
                if target.is_symlink() or not target.is_file():
                    raise ValueError('Required resource missing or symlinked')
            run('iconutil', '-c', 'icns', iconset, '-o', resources / icon)
            patch_asar(resources / 'app.asar', (output / 'robot.png').read_bytes())
            records = info.get('ElectronAsarIntegrity', {})
            if 'Resources/app.asar' in records:
                if records['Resources/app.asar'].get('algorithm') != 'SHA256':
                    raise ValueError('Unsupported bundle integrity algorithm')
                records['Resources/app.asar']['hash'] = header_hash(resources / 'app.asar')
                info_path.write_bytes(plistlib.dumps(info))
            run('codesign', '--force', '--sign', '-', '--preserve-metadata=identifier,entitlements,requirements,flags,runtime', stage)
            verify_app(stage)
            if (resources / icon).read_bytes()[:4] != b'icns':
                raise ValueError('Invalid ICNS output')
            parked = app.with_name('.' + app.name + '.robot-rollback-' + stamp)
            app.rename(parked)
            stage.rename(app)
            installed = True
            verify_app(app)
            config = state / 'last.json'
            pending = state / 'last.json.pending'
            pending.write_text(json.dumps({'app': str(app), 'accent': accent.upper(), 'backup': str(backup)}, indent=2) + '\n')
            pending.replace(config)
            obsolete = parked
            parked = None
            try:
                shutil.rmtree(obsolete)
            except OSError:
                print('Verified install; old sibling copy could not be removed:', obsolete, file=sys.stderr)
        return backup
    except BaseException:
        if parked and parked.exists():
            if installed and app.exists():
                shutil.rmtree(app)
            parked.rename(app)
        raise
    finally:
        lock.rmdir()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--render-only', action='store_true')
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--reapply', action='store_true')
    parser.add_argument('--accent', help='Exact #RRGGBB accent; quote the value')
    parser.add_argument('--app', type=pathlib.Path, help='Explicit macOS app bundle')
    parser.add_argument('--output', type=pathlib.Path, help='Render output directory')
    args = parser.parse_args()
    state = pathlib.Path(os.environ.get('HERMES_HOME', pathlib.Path.home() / '.hermes')) / 'custom-icon'
    try:
        if args.reapply:
            if args.app or args.accent or args.output:
                parser.error('--reapply uses only the saved local target and accent')
            saved = json.loads((state / 'last.json').read_text())
            args.app, args.accent = pathlib.Path(saved['app']), saved['accent']
        if not args.accent:
            parser.error('--accent is required')
        palette(args.accent)
        if args.render_only:
            if not args.output or args.app:
                parser.error('--render-only requires --output and does not accept --app')
            render(args.accent, args.output)
            print('Verified SVG and 1024px PNG:', args.output)
        else:
            if not args.app or args.output:
                parser.error('--apply requires --app and does not accept --output')
            backup = apply(args.app, args.accent, state)
            print('Verified installation. Backup:', backup)
            print('Restart the app manually to load the icon; no running process was stopped.')
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr.decode(errors='replace') if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else str(exc)
        parser.exit(1, 'Error: ' + detail + '\n')


if __name__ == '__main__':
    main()


