#!/usr/bin/env python3
"""Strict source patch installer; dry-run by default. Never fetches or runs Codex."""
from pathlib import Path
import argparse
import difflib
import hashlib
import json
import os
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT/'adapters/codex-native/manifest.json').read_text())

OLD_CALL = '''
        let (mut outcome, analytics) = run_guardian_review_session_before_deadline(
            Arc::clone(&self.session),
            self.context.clone(),
            prepared.request.clone(),
            self.reasons.clone(),
            guardian_output_schema(),
            Some(cancellation.clone()),
            deadline,
        )
        .await;
'''
NEW_CALL = '''
        let jev_outcome = super::super::jev::review(
            self.session.as_ref(),
            &self.context,
            &prepared.request,
            &self.reasons,
            &self.options,
            &prepared.jev_review_id,
            deadline,
            cancellation,
        )
        .await;
        let (mut outcome, analytics) = if let Some(outcome) = jev_outcome {
            (outcome, GuardianReviewAnalyticsResult::without_session())
        } else {
            run_guardian_review_session_before_deadline(
                Arc::clone(&self.session),
                self.context.clone(),
                prepared.request.clone(),
                self.reasons.clone(),
                guardian_output_schema(),
                Some(cancellation.clone()),
                deadline,
            )
            .await
        };
'''

def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()

def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError('Patch anchor missing or ambiguous; no files changed.')
    return text.replace(old, new, 1)

def transform(path: str, text: str) -> str:
    if path.endswith('/mod.rs'):
        return replace_once(text, 'mod decision;\n', 'mod decision;\nmod jev;\n')
    text = replace_once(text, 'pub(in crate::guardian) struct PreparedApproval {\n',
        'pub(in crate::guardian) struct PreparedApproval {\n    jev_review_id: String,\n')
    text = replace_once(text, '            PreparedApproval {\n',
        '            PreparedApproval {\n                jev_review_id: review_id.to_owned(),\n')
    return replace_once(text, OLD_CALL, NEW_CALL)

def plan(repo: Path) -> dict[str, tuple[bytes, bytes]]:
    head = subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'], text=True).strip()
    if head != MANIFEST['inspected_commit']:
        raise ValueError('Codex HEAD differs from inspected commit. Rebase/review the adapter; do not bypass this check.')
    changes = {}
    for name, expected in MANIFEST['expected_git_blobs'].items():
        p = repo/name
        if p.is_symlink():
            raise ValueError('Refusing symlink source')
        data = p.read_bytes()
        if git_blob(data) != expected:
            raise ValueError('Source blob mismatch: '+name)
        changes[name] = (data, transform(name, data.decode()).encode())
    new = MANIFEST['new_file']
    if (repo/new).exists():
        raise ValueError('Native JEV module already exists; inspect instead of overwriting.')
    changes[new] = (b'', (ROOT/'adapters/codex-native/jev.rs').read_bytes())
    return changes

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--apply', action='store_true')
    args = p.parse_args()
    repo = args.repo.expanduser().resolve()
    try:
        changes = plan(repo)
        for name,(old,new) in changes.items():
            sys.stdout.writelines(difflib.unified_diff(old.decode().splitlines(True),new.decode().splitlines(True),
                fromfile='a/'+name if old else '/dev/null',tofile='b/'+name))
        if not args.apply:
            print('\nDry run only. Add --apply to write these source files.',file=sys.stderr)
            return 0
        applied = []
        try:
            for name,(old,new) in changes.items():
                path = repo/name
                temp = path.with_name(path.name+'.jev-tmp')
                if temp.exists():
                    raise ValueError('Temporary path exists; inspect it before retrying.')
                with temp.open('xb') as f:
                    f.write(new)
                os.replace(temp, path)
                applied.append(name)
        except BaseException:
            for name in reversed(applied):
                old = changes[name][0]
                if old: (repo/name).write_bytes(old)
                else: (repo/name).unlink(missing_ok=True)
            raise
        print('\nSource patch applied. Native compilation and tests must pass before use.',file=sys.stderr)
        return 0
    except (ValueError,OSError,subprocess.CalledProcessError) as exc:
        print(str(exc),file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
