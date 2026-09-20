from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from .config import Config
from .schema import Envelope, ContractError, MAX_INPUT_BYTES, strict_json, canonical, digest
from .daemon import make_engine, remote_review, serve
from .hooks import hook_envelope, permission_output
from .questions import QUESTION_HASH, QUESTIONS


def run_review(raw: dict, cfg: Config) -> dict:
    env = Envelope.parse(raw)
    if cfg.daemon_url and cfg.mode != 'off' and cfg.allow_remote_context:
        return remote_review(env, cfg)
    return make_engine(cfg).review(env).json()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='JEV approval preflight; never executes actions')
    subs = parser.add_subparsers(dest='command', required=True)
    for name in ('review', 'native', 'hook', 'serve', 'doctor'):
        p = subs.add_parser(name)
        p.add_argument('--config', required=True, help='Absolute path to owner-controlled TOML')
    p = subs.add_parser('questions')
    p.add_argument('--json', action='store_true')
    p = subs.add_parser('policy-hash')
    p.add_argument('envelope', type=Path)
    args = parser.parse_args(argv)
    request_id = ''
    try:
        if args.command == 'questions':
            print(json.dumps(QUESTIONS, indent=2) if args.json else QUESTION_HASH)
            return 0
        if args.command == 'policy-hash':
            env = Envelope.parse(strict_json(args.envelope.read_bytes()))
            print(env.policy_hash)
            return 0
        cfg = Config.load(Path(args.config).expanduser())
        if args.command == 'serve':
            serve(cfg)
            return 0
        if args.command == 'doctor':
            import os
            print(json.dumps({
                'mode': cfg.mode, 'model': cfg.model,
                'remote_context_authorized': cfg.allow_remote_context,
                'api_key_present': bool(os.environ.get('TYPESAFE_API_KEY')),
                'daemon_selected': bool(cfg.daemon_url),
                'question_set_approved': cfg.approved_question_hash == QUESTION_HASH,
                'approved_policy_count': len(cfg.approved_policy_hashes),
                'audit_configured': bool(cfg.audit_path),
                'live_provider_test_performed': False,
            }, indent=2))
            return 0
        raw = strict_json(sys.stdin.buffer.read(MAX_INPUT_BYTES + 1))
        if isinstance(raw, dict):
            request_id = raw.get('request_id', '')
        if args.command == 'hook':
            result = make_engine(cfg).review(hook_envelope(raw)).json()
            print(json.dumps(permission_output(result)))
        else:
            print(json.dumps(run_review(raw, cfg), separators=(',', ':')))
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception:
        # Approval protocol gets an explicit abstention, never a success-shaped allow.
        if args.command == 'hook':
            print('{}')
            return 0
        if args.command == 'native':
            print(json.dumps({'schema_version': 1, 'request_id': request_id if isinstance(request_id, str) else '',
                              'decision': 'defer', 'reason': 'adapter_failure'}))
            return 0
        print('JEV approval: configuration, input, or transport validation failed.', file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
