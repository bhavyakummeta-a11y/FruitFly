"""Experimental dopamine-gated KC->MBON depression, with no backpropagation.

Only specified existing KC->MBON entries may change. The cell-type pairs below
are compartment approximations, not synapse-local dopamine reconstructions.
"""
import hashlib
import json
import math
from pathlib import Path
import os
import tempfile
from .brain import ConnectomeBrain
from .core import clip

LEARNING_INPUTS = {'kc': ('cell_type', ['KC*'], None),
                   'reward': ('cell_type', ['PAM01'], None),
                   'punishment': ('cell_type', ['PPL101'], None)}
LEARNING_READOUTS = {'reward_mbon': ('cell_type', ['MBON01'], None),
                     'punishment_mbon': ('cell_type', ['MBON11'], None)}


class Plasticity:
    """Bounded LTD, gated by measured DAN firing and explicit reinforcement.

    factors *= 1 - learning_rate * clipped_KC_spikes/5 * clipped_DAN_Hz/200
    A factor cannot fall below 0.2 or exceed 1. Signs and topology stay fixed.
    """
    def __init__(self, weights, groups, learning_rate=.1):
        import numpy as np
        if not math.isfinite(learning_rate) or not 0 < learning_rate <= 1:
            raise ValueError('Learning rate must be in (0,1]')
        if not np.issubdtype(weights.dtype, np.floating):
            raise ValueError('Plasticity requires floating-point weights')
        self.w, self.rate = weights, learning_rate
        self.channels = {}
        for signal, output in [('reward','reward_mbon'),('punishment','punishment_mbon')]:
            positions, sources = [], []
            targets = set(groups[output])
            for kc in groups['kc']:
                for pos in range(weights.indptr[kc],weights.indptr[kc+1]):
                    if weights.indices[pos] in targets and weights.data[pos] != 0:
                        positions.append(pos); sources.append(kc)
            if not positions:
                raise ValueError(f'No KC->MBON connections for {signal}')
            self.channels[signal] = (np.array(positions,dtype=int),np.array(sources,dtype=int))
        self.positions = np.unique(np.concatenate([v[0] for v in self.channels.values()]))
        self.original = weights.data[self.positions].copy()
        self.floor = .2
        digest=hashlib.sha256()
        for array in [weights.indptr,weights.indices,weights.data]:
            digest.update(array.tobytes())
        self.fingerprint=digest.hexdigest()
        self.updates=0

    def update(self, eligible_counts, dan_hz, reinforcement):
        import numpy as np
        if not math.isfinite(reinforcement) or not -1 <= reinforcement <= 1:
            raise ValueError('Reinforcement must be finite and in [-1,1]')
        if not math.isfinite(dan_hz) or dan_hz < 0:
            raise ValueError('Dopamine rate must be finite and nonnegative')
        eligible_counts=np.asarray(eligible_counts)
        if eligible_counts.shape != (self.w.shape[0],) or not np.isfinite(eligible_counts).all() or (eligible_counts < 0).any():
            raise ValueError('Invalid KC eligibility counts')
        if reinforcement == 0:
            return 0
        signal='reward' if reinforcement>0 else 'punishment'
        positions,sources=self.channels[signal]
        base=self.original[np.searchsorted(self.positions,positions)]
        before=self.w.data[positions].copy()
        activity=np.clip(eligible_counts[sources]/5,0,1)
        gate=min(dan_hz/200,1)*abs(reinforcement)
        factors=before/base
        self.w.data[positions]=base*np.maximum(self.floor,factors*(1-self.rate*activity*gate))
        changed=int(np.count_nonzero(before!=self.w.data[positions]))
        self.updates += bool(changed)
        return changed

    def save(self,path):
        import numpy as np
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        metadata=json.dumps({'version':1,'fingerprint':self.fingerprint,'updates':self.updates,
                             'learning_rate':self.rate,'floor':self.floor})
        with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as out:
            temporary=out.name
            np.savez_compressed(out,metadata=metadata,positions=self.positions,
                                factors=self.w.data[self.positions]/self.original)
        try:
            os.replace(temporary,path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def load(self,path):
        import numpy as np
        with np.load(path,allow_pickle=False) as archive:
            metadata=json.loads(str(archive['metadata']))
            factors=archive['factors']
            if (metadata.get('version')!=1 or metadata.get('fingerprint')!=self.fingerprint
                    or not np.array_equal(archive['positions'],self.positions)):
                raise ValueError('Checkpoint does not match the connectome and plasticity mask')
            if factors.shape!=self.original.shape or not np.isfinite(factors).all() or (factors<self.floor).any() or (factors>1).any():
                raise ValueError('Invalid checkpoint weight factors')
            updates = int(metadata['updates'])
            rate = float(metadata['learning_rate'])
            if updates < 0 or not math.isfinite(rate) or not 0 < rate <= 1 or metadata.get('floor') != self.floor:
                raise ValueError('Invalid checkpoint learning parameters')
            self.w.data[self.positions]=self.original*factors
            self.updates=updates
            self.rate=rate

    def summary(self):
        import numpy as np
        factors=self.w.data[self.positions]/self.original
        return {'plastic_edges':len(self.positions),'changed_edges':int(np.count_nonzero(factors!=1)),
                'minimum_factor':float(factors.min()),'updates':self.updates}


class LearningBrain(ConnectomeBrain):
    def __init__(self,directory,seed=0,ms=200,learning_rate=.1):
        super().__init__(directory,seed=seed,ms=ms,extra_inputs=LEARNING_INPUTS,
                         extra_readouts=LEARNING_READOUTS)
        self.w = self.w.astype(float)
        self.plasticity=Plasticity(self.w,self.groups,learning_rate)
        self.name='CONNECTOME LIF + EXPERIMENTAL KC→MBON LEARNING'

    def reinforce(self,reward):
        """Credit preceding sensory trial; run a separate DAN stimulation trial.

        Eligible KC activity comes from the decision, not from reward stimulation.
        Caller must hold/pause physics during BOTH feedback and decision trials.
        """
        if not math.isfinite(reward) or not -1 <= reward <= 1:
            raise ValueError('Reward must be finite and in [-1,1]')
        if reward==0:
            return {'reward':0.0,'dan_hz':0.0,'changed_edges':0}
        eligible=self.last_counts.copy()
        signal='reward' if reward>0 else 'punishment'
        rates=self.run({signal:200*abs(reward)},[signal])
        changed=self.plasticity.update(eligible,rates[signal],reward)
        return {'reward':reward,'dan_hz':rates[signal],'changed_edges':changed}


def flight_reward(previous,current,heading,clearance,collision=False):
    """Engineering reward, not a biological measurement. Evaluate in sim time."""
    if collision:
        return -1.0
    dt=current.time-previous.time
    if dt<=0:
        return 0.0
    progress=((current.east-previous.east)*math.sin(heading)
              +(current.north-previous.north)*math.cos(heading))
    forward=clip(progress/(max(previous.speed,1)*dt),-1,1)
    close=clip((250-clearance)/250,0,1)
    bank=clip((abs(current.roll)-math.radians(18))/math.radians(25),0,1)
    descent=clip(-current.climb/5,0,1)
    slow=clip((.85*previous.speed-current.speed)/max(.2*previous.speed,1),0,1)
    return clip(.2*forward-.6*close-.4*bank-.4*descent-.4*slow,-1,1)
