"""Local conditioning experiment with synthetic KC cues and frozen controls.

This demonstrates neural plasticity, not trained autonomous aircraft control.
It never connects to FlightGear or pushes logs to GitHub.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from .learning import LearningBrain


def evaluate(brain,trials,seed):
    saved_seed,saved_calls=brain.seed,brain.calls
    brain.seed,brain.calls=seed,0
    rows=[]
    try:
        for trial in range(trials):
            for cue in ['cue_good','cue_bad']:
                rates=brain.run({cue:150},['reward_mbon','punishment_mbon','DNp01'])
                rows.append({'trial':trial,'cue':cue,**rates})
    finally:
        brain.seed,brain.calls=saved_seed,saved_calls
    return rows


def experiment(args):
    output=Path(args.output)
    output.mkdir(parents=True,exist_ok=False)
    brain=LearningBrain(args.data,seed=args.seed,learning_rate=args.learning_rate)
    # Explicit artificial sensory representation, not a claim about odor/vision.
    candidates=brain.groups['kc']
    cue_size=min(64,len(candidates)//2)
    # Targeted artificial cues: choose KCs with strong existing connections to
    # each measured MBON group. This is assay design, not learned sensory coding.
    reward_strength=np.asarray(brain.w[candidates][:,brain.groups['reward_mbon']].sum(axis=1)).ravel()
    good=candidates[np.argsort(-reward_strength,kind='stable')[:cue_size]]
    remaining=candidates[~np.isin(candidates,good)]
    punishment_strength=np.asarray(brain.w[remaining][:,brain.groups['punishment_mbon']].sum(axis=1)).ravel()
    bad=remaining[np.argsort(-punishment_strength,kind='stable')[:cue_size]]
    chosen=np.concatenate([good,bad])
    for name,indices in [('cue_good',chosen[:cue_size]),('cue_bad',chosen[cue_size:])]:
        brain.input_specs[name]=brain.input_specs['kc']
        brain.groups[name]=indices
    print(f'Loaded {brain.n} neurons; {brain.plasticity.summary()}',flush=True)
    print('Evaluating frozen baseline on held-out RNG seeds...',flush=True)
    frozen=evaluate(brain,args.trials,args.seed+100000)
    records=[]
    for episode in range(args.episodes):
        for cue,signal,reward in [('cue_good','reward',1.0),('cue_bad','punishment',-1.0)]:
            brain.run({cue:150},['reward_mbon','punishment_mbon'])
            feedback=brain.reinforce(reward)
            changed=feedback['changed_edges']
            row={'episode':episode,'cue':cue,'reinforcement':reward,'dan_hz':feedback['dan_hz'],
                 'edges_changed_this_trial':changed,**brain.plasticity.summary()}
            records.append(row)
            print(json.dumps(row),flush=True)
        brain.plasticity.save(output/'checkpoint.npz')
        (output/'training.json').write_text(json.dumps(records,indent=2)+'\n')
    print('Evaluating trained brain with updates disabled and the same held-out seeds...',flush=True)
    learned=evaluate(brain,args.trials,args.seed+100000)
    differences=[{'trial':a['trial'],'cue':a['cue'],
                  **{key:b[key]-a[key] for key in ['reward_mbon','punishment_mbon','DNp01']}}
                 for a,b in zip(frozen,learned)]
    trained_values=brain.w.data[brain.plasticity.positions].copy()
    try:
        brain.w.data[brain.plasticity.positions]=brain.plasticity.original
        digest=hashlib.sha256()
        for array in [brain.w.indptr,brain.w.indices,brain.w.data]:
            digest.update(array.tobytes())
        unchanged=digest.hexdigest()==brain.plasticity.fingerprint
    finally:
        brain.w.data[brain.plasticity.positions]=trained_values
    if not unchanged:
        raise RuntimeError('A non-plastic weight or matrix topology changed')
    result={'nonplastic_weights_unchanged':unchanged,'experiment':'synthetic KC cue conditioning; not flight performance',
            'seed':args.seed,'episodes':args.episodes,'trials':args.trials,
            'cue_indices':{'good':chosen[:cue_size].tolist(),'bad':chosen[cue_size:].tolist()},
            'fingerprint':brain.plasticity.fingerprint,'frozen':frozen,'learned':learned,
            'learned_minus_frozen_hz':differences,'plasticity':brain.plasticity.summary(),
            'flight_improvement_demonstrated':False}
    (output/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'Results: {output / "results.json"}',flush=True)
    print(json.dumps(result['plasticity'],indent=2))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',default='data/brain')
    p.add_argument('--output',required=True,help='New local output directory, must not exist')
    p.add_argument('--episodes',type=int,default=4)
    p.add_argument('--trials',type=int,default=3)
    p.add_argument('--seed',type=int,default=0)
    p.add_argument('--learning-rate',type=float,default=.1)
    args=p.parse_args()
    if args.episodes<1 or args.trials<1:
        p.error('--episodes and --trials must be positive')
    try:
        experiment(args)
    except (OSError,ValueError,RuntimeError) as exc:
        print(f'Error: {exc}',file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':
    sys.exit(main())
