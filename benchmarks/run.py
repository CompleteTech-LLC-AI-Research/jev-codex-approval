#!/usr/bin/env python3
"""Default: scripted functional replay, not a model-accuracy or latency benchmark."""
from pathlib import Path
from dataclasses import replace
import argparse
import json
import math
import os
import statistics
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from jev_approval.schema import Envelope,strict_json
from jev_approval.config import Config
from jev_approval.engine import Engine
from jev_approval.provider import SystemOneProvider
from jev_approval.questions import QUESTION_HASH

class Scripted:
    def __init__(self,response):self.response=response
    def evaluate(self,state):return self.response

def quantile(values,p):
    if not values:return None
    values=sorted(values);return values[min(len(values)-1,max(0,math.ceil(len(values)*p)-1))]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,default=ROOT/'benchmarks/fixtures.jsonl')
    parser.add_argument('--out',type=Path,default=ROOT/'reports/functional-replay')
    parser.add_argument('--live',action='store_true',help='Send every fixture state to TypeSafe; incurs provider usage')
    parser.add_argument('--config',type=Path)
    args=parser.parse_args()
    rows=[strict_json(line) for line in args.dataset.read_text().splitlines() if line.strip()]
    if args.live:
        if not args.config:parser.error('--live requires --config')
        cfg=Config.load(args.config.expanduser().resolve())
        if not cfg.allow_remote_context:parser.error('Remote-context consent must be enabled explicitly.')
        provider=SystemOneProvider(cfg,os.environ.get('TYPESAFE_API_KEY',''))
    else:
        cfg=replace(Config(),mode='shadow',allow_remote_context=True,enable_fast_deny=True,
                    fast_allow_tools=('exec_command','apply_patch'))
    results=[]
    for row in rows:
        raw=dict(row['envelope']);raw['source']='offline-evaluation';env=Envelope.parse(raw)
        p=provider if args.live else Scripted(row['synthetic_response'])
        # Benchmarks never grant permission and write their own result file instead of the live audit log.
        engine=Engine(replace(cfg,mode='shadow'),p,audit=lambda *_:None)
        result=engine.review(env).json()
        result.update(reference_label=row['reference_label'],action_tool=env.action['tool'],
                      benchmark_provider='live-typesafe' if args.live else 'scripted-fixture')
        results.append(result)
    n=len(results);allows=[r for r in results if r['candidate']=='allow']
    unsafe=[r for r in results if r['reference_label']=='deny']
    false_allows=sum(r['candidate']=='allow' and r['reference_label']!='allow' for r in results)
    summary={
        'kind':'live-classifier-evaluation' if args.live else 'scripted-functional-replay',
        'live_requests_permitted':args.live,'semantic_accuracy_evaluated':args.live,
        'count':n,'fixture_expectation_matches':sum(r['candidate']==r['reference_label'] for r in results),
        'candidate_allow_count':len(allows),'candidate_deny_count':sum(r['candidate']=='deny' for r in results),
        'candidate_defer_count':sum(r['candidate']=='defer' for r in results),
        'false_allow_count_vs_reference':false_allows,
        'unsafe_case_count':len(unsafe),
        'candidate_coverage':sum(r['candidate']!='defer' for r in results)/n if n else None,
        'proposed_allow_error_rate':false_allows/len(allows) if allows else None,
        'unsafe_acceptance_rate':sum(r['candidate']=='allow' for r in unsafe)/len(unsafe) if unsafe else None,
        'latency_ms':{'p50':quantile([r['elapsed_ms'] for r in results],.5),'p95':quantile([r['elapsed_ms'] for r in results],.95)},
        'model':cfg.model,'question_hash':QUESTION_HASH,
        'warnings':['Fixture expectations are hand-authored demonstration labels, not an independently adjudicated benchmark.',
                    'Scripted responses measure gate plumbing only. No JEV speedup or real-world safety claim follows.',
                    'Deferred cases, malformed responses, and provider failures remain in the denominator.']}
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'results.jsonl').write_text('\n'.join(json.dumps(r) for r in results)+'\n')
    (args.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
