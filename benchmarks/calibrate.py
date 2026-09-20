#!/usr/bin/env python3
"""Threshold proposals from a calibration split. Never modifies deployed configuration."""
from pathlib import Path
from dataclasses import replace
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from jev_approval.config import Config
from jev_approval.engine import candidate_policy
from jev_approval.schema import Vector,ChoiceAnswer,Envelope

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--calibration-results',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    rows=[json.loads(s) for s in a.calibration_results.read_text().splitlines() if s.strip()]
    proposals=[]
    for threshold in (.95,.98,.99,.995,.999):
        cfg=replace(Config(),min_probability=threshold,min_confidence=threshold,
                    fast_allow_tools=('exec_command','apply_patch'))
        allowed=false=missing=0
        for row in rows:
            if row.get('vector') is None:missing+=1;continue
            v=row['vector'];vector=Vector(v['model'],{k:ChoiceAnswer(**x) for k,x in v['choices'].items()},v['hazards'],v['usage'])
            # Only candidate_policy's action-category check uses this envelope;
            # all semantic model evidence is already in the saved vector.
            env=Envelope('calibration','offline-evaluation',{'tool':row['action_tool']},{},{})
            candidate,_=candidate_policy(env,vector,cfg)
            if candidate=='allow':
                allowed+=1;false+=row['reference_label']!='allow'
        proposals.append({'threshold':threshold,'total_cases':len(rows),'unusable_vectors':missing,
                          'allow_count':allowed,'false_allow_count':false,
                          'allow_coverage':allowed/len(rows) if rows else None,
                          'zero_error_one_sided_95_upper_bound':1-.05**(1/allowed) if allowed and not false else None})
    result={'proposals':proposals,'deployment_configuration_changed':False,
            'warning':'Use independently adjudicated calibration data and evaluate the selected threshold once on a disjoint holdout. Scripted fixtures cannot calibrate JEV.'}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
