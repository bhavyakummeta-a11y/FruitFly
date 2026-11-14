import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import numpy as np
from scipy.sparse import csr_matrix
from flight_simulator.learning import Plasticity, LearningBrain, flight_reward
from flight_simulator.core import State


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.w=csr_matrix((np.array([10,8,6,4,3,2],dtype=float),
                           ([0,0,1,1,0,4],[2,3,2,3,6,2])),shape=(7,7))
        self.groups={'kc':np.array([0,1]),'reward_mbon':np.array([2]),'punishment_mbon':np.array([3])}
        self.p=Plasticity(self.w,self.groups,learning_rate=.5)
        self.original=self.w.copy()
        self.eligibility=np.array([5,0,0,0,0,0,0])

    def test_reward_changes_only_active_kc_reward_mbon_edge(self):
        self.assertEqual(self.p.update(self.eligibility,200,1),1)
        diff=(self.w-self.original).tocoo()
        self.assertEqual(list(zip(diff.row,diff.col)),[(0,2)])
        self.assertEqual(self.w[0,2],5)
        self.assertTrue(np.array_equal(self.w.indices,self.original.indices))
        self.assertTrue(np.array_equal(self.w.indptr,self.original.indptr))

    def test_punishment_uses_distinct_compartment(self):
        self.p.update(self.eligibility,200,-1)
        diff=(self.w-self.original).tocoo()
        self.assertEqual(list(zip(diff.row,diff.col)),[(0,3)])

    def test_no_reward_no_dopamine_or_no_eligibility_means_no_learning(self):
        for counts,dan,reward in [(self.eligibility,200,0),(self.eligibility,0,1),(np.zeros(7),200,-1)]:
            self.assertEqual(self.p.update(counts,dan,reward),0)
        np.testing.assert_array_equal(self.w.data,self.original.data)

    def test_bounded_weights_and_unrelated_connections_stay_fixed(self):
        for _ in range(100):
            self.p.update(np.ones(7)*10,1000,1)
            self.p.update(np.ones(7)*10,1000,-1)
        np.testing.assert_allclose(self.w.data[self.p.positions],self.original.data[self.p.positions]*.2)
        others=np.ones(len(self.w.data),dtype=bool);others[self.p.positions]=False
        np.testing.assert_array_equal(self.w.data[others],self.original.data[others])

    def test_checkpoint_restore_and_wrong_connectome_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'checkpoint.npz'
            self.p.update(self.eligibility,200,1);self.p.save(path)
            restore=Plasticity(self.original.copy(),self.groups)
            restore.load(path)
            np.testing.assert_array_equal(restore.w.data,self.w.data)
            incompatible=self.original.copy();incompatible.data[-1]+=1
            other=Plasticity(incompatible,self.groups)
            with self.assertRaisesRegex(ValueError,'does not match'):
                other.load(path)
            with np.load(path,allow_pickle=False) as archive:
                metadata=str(archive['metadata']); positions=archive['positions'].copy()
                factors=archive['factors'].copy()
            factors[0]=math.nan
            np.savez(path,metadata=metadata,positions=positions,factors=factors)
            before=restore.w.data.copy()
            with self.assertRaisesRegex(ValueError,'Invalid checkpoint'):
                restore.load(path)
            np.testing.assert_array_equal(before,restore.w.data)

    def test_feedback_credits_decision_not_reward_induced_spikes(self):
        brain=LearningBrain.__new__(LearningBrain)
        brain.last_counts=self.eligibility.copy()
        brain.plasticity=self.p
        def feedback_run(inputs,readouts):
            brain.last_counts=np.array([0,5,0,0,0,0,0])
            return {'reward':200}
        brain.run=Mock(side_effect=feedback_run)
        result=brain.reinforce(1)
        self.assertEqual(result['changed_edges'],1)
        self.assertEqual(self.w[0,2],5)
        self.assertEqual(self.w[1,2],6)
        brain.run.assert_called_once_with({'reward':200},['reward'])

    def test_invalid_inputs_fail_without_weight_mutation(self):
        for reward in [math.nan,2]:
            with self.assertRaises(ValueError): self.p.update(self.eligibility,200,reward)
        with self.assertRaises(ValueError): self.p.update(np.ones(2),200,1)
        with self.assertRaises(ValueError): Plasticity(self.w.astype(int),self.groups)
        np.testing.assert_array_equal(self.w.data,self.original.data)

    def test_flight_reward_rewards_progress_and_penalizes_danger(self):
        previous=State()
        stable=State(time=1,north=50)
        self.assertGreater(flight_reward(previous,stable,0,500),0)
        unsafe=State(time=1,north=0,roll=1,climb=-10,speed=20)
        self.assertLess(flight_reward(previous,unsafe,0,20),0)
        self.assertEqual(flight_reward(previous,stable,0,0,collision=True),-1)
        self.assertEqual(flight_reward(previous,previous,0,500),0)


if __name__=='__main__':
    unittest.main()
