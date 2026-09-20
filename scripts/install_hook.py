#!/usr/bin/env python3
"""Install an abstaining Codex compatibility hook, with backup and explicit apply."""
from pathlib import Path
import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
ROOT = Path(__file__).resolve().parents[1]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--codex-home', type=Path, default=Path.home()/'.codex')
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--apply', action='store_true')
    p.add_argument('--remove', action='store_true')
    args = p.parse_args()
    config = args.config.expanduser().resolve()
    if not config.is_file():
        p.error('Create the TOML config first.')
    home = args.codex_home.expanduser().resolve()
    target = home/'hooks.json'
    if target.is_symlink():
        p.error('Refusing symlink hooks.json')
    data = json.loads(target.read_text()) if target.exists() else {}
    groups = data.setdefault('hooks', {}).setdefault('PermissionRequest', [])
    marker = 'JEV compatibility (abstains; native integration required)'
    groups[:] = [g for g in groups if not any(h.get('statusMessage') == marker for h in g.get('hooks', []))]
    cmd = [str(Path(sys.executable).resolve()), '-I', str(ROOT/'scripts/launcher.py'),
           'hook', '--config', str(config)]
    if not args.remove:
        groups.append({'matcher': '*', 'hooks': [{'type': 'command',
            'command': shlex.join(cmd), 'commandWindows': subprocess.list2cmdline(cmd),
            'timeout': 3, 'statusMessage': marker}]})
    rendered = json.dumps(data, indent=2) + '\n'
    if not args.apply:
        print(rendered)
        print('Dry run. Add --apply to write this configuration. This hook never auto-allows.', file=sys.stderr)
        return
    home.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.copy2(target, target.with_name('hooks.json.backup.'+str(time.time_ns())))
    temp = target.with_name('.hooks.json.'+str(os.getpid())+'.tmp')
    try:
        with temp.open('x') as f:
            os.chmod(temp, 0o600)
            f.write(rendered)
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    print(str(target))
    print('Review the new hook with /hooks. No hook-trust bypass is configured.')

if __name__ == '__main__':
    main()
