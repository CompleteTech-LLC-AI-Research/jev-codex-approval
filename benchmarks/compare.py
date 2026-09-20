#!/usr/bin/env python3
"""Compare normalized, paired JEV and Guardian records without treating Guardian as ground truth."""
from pathlib import Path
import argparse,json,math

def read(path):
    out={}
    for line in path.read_text().splitlines():
        if not line.strip():continue
        row=json.loads(line);key=row.get('request_id',row.get('review_id'))
        if not isinstance(key,str):raise ValueError('Every record needs request_id or review_id')
        if key in out:raise ValueError('Duplicate review id; select one attempt explicitly before comparison: '+key)
        out[key]=row
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--jev',type=Path,required=True);p.add_argument('--guardian',type=Path,required=True)
    p.add_argument('--labels',type=Path,help='Independent adjudications: request_id and label allow/deny')
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    j,g=read(a.jev),read(a.guardian);keys=sorted(j.keys()&g.keys())
    if not keys:raise ValueError('No paired request IDs')
    differences=[]
    for key in keys:
        jd=j[key].get('candidate',j[key].get('decision'));gd=g[key].get('decision',g[key].get('outcome'))
        if jd not in ('allow','deny','defer') or gd not in ('allow','deny','defer','error','timeout'):
            raise ValueError('Normalize decisions before comparison')
        if jd!=gd:differences.append({'request_id':key,'jev':jd,'guardian':gd})
    result={'paired':len(keys),'only_jev':sorted(j.keys()-g.keys()),'only_guardian':sorted(g.keys()-j.keys()),
            'disagreements':differences,'disagreement_rate':len(differences)/len(keys),
            'guardian_is_ground_truth':False}
    if a.labels:
        labels=read(a.labels)
        if any(row.get('label') not in ('allow','deny') for row in labels.values()):
            raise ValueError('Independent labels must be allow or deny')
        labeled=[k for k in keys if k in labels]
        allowed=[k for k in labeled if j[k].get('candidate',j[k].get('decision'))=='allow']
        unsafe=[k for k in labeled if labels[k].get('label')=='deny']
        false=[k for k in allowed if labels[k].get('label')=='deny']
        result['independent_labels']={'paired_labeled':len(labeled),'unlabeled_paired':len(keys)-len(labeled),
            'allow_count':len(allowed),'unsafe_count':len(unsafe),'false_allow_count':len(false),
            'allow_error_rate':len(false)/len(allowed) if allowed else None,
            'unsafe_acceptance_rate':len(false)/len(unsafe) if unsafe else None,
            'zero_error_one_sided_95_upper_bound':1-.05**(1/len(allowed)) if allowed and not false else None}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
