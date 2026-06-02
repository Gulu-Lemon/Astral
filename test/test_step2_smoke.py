"""Smoke test for Step 2: ActionPlan engine."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state import (WorldState, AgentState, ActionStep, ActionPlan,
                   IntentType, EvidenceItem, TrialState, Evidence)
from agent_engine import NPCAgent, _parse_intent_type
from arbiter import Arbiter
from session import _time_string

def test_intent_types():
    assert _parse_intent_type('search') == IntentType.SEARCH
    assert _parse_intent_type('guard') == IntentType.GUARD
    assert _parse_intent_type('interrogate') == IntentType.INTERROGATE
    assert _parse_intent_type('watch') == IntentType.WATCH
    assert _parse_intent_type('attack') == IntentType.ATTACK
    print("IntentType: OK")

def test_plan_data_structures():
    s = ActionStep(action_type='MOVE', target_location='Lobby', duration=10, description='test')
    d = s.to_dict()
    s2 = ActionStep.from_dict(d)
    assert s2.action_type == 'MOVE'
    assert s2.duration == 10

    p = ActionPlan(agent_id='No.01', steps=[s], step_start_time=420)
    d = p.to_dict()
    p2 = ActionPlan.from_dict(d)
    assert len(p2.steps) == 1
    assert p2.steps[0].action_type == 'MOVE'
    print("Plan data structures: OK")

def test_conflict_detection():
    class DummyAgent:
        def __init__(self, aid, state):
            self.agent_id = aid
            self.state = state

    a = Arbiter(None)
    agents = {
        'No.01': DummyAgent('No.01', AgentState(agent_id='No.01', name='A',
            current_plan=ActionPlan(agent_id='No.01', steps=[
                ActionStep(action_type='CONFRONT', target_id='No.02', target_location='Hall', duration=10)
            ]))),
        'No.02': DummyAgent('No.02', AgentState(agent_id='No.02', name='B',
            current_plan=ActionPlan(agent_id='No.02', steps=[
                ActionStep(action_type='SOCIALIZE', target_id=None, target_location='Hall', duration=10)
            ]))),
    }
    world = WorldState()
    world.npc_locations['No.01'] = 'Hall'
    world.npc_locations['No.02'] = 'Hall'

    conflicts = a.detect_plan_conflicts(agents, world)
    assert len(conflicts) >= 1
    assert conflicts[0]['type'] in ('confrontation', 'social_opportunity')
    print(f"Conflict detection: OK ({len(conflicts)} conflicts found)")

def test_time_string():
    assert '7' in _time_string(420)   # 7:00 = 上午7点
    assert '12' in _time_string(720)  # 12:00 = 中午12点
    assert '6' in _time_string(1080)  # 18:00 = 下午6点
    assert '22' in _time_string(1320) # 22:00 = 晚上22点
    s = _time_string(435)  # 7:15
    assert '7' in s and '15' in s
    print("time_string: OK")

def test_trial_state_no_closing():
    ts = TrialState(phase='investigation', victim_id='No.03',
                    timer_start=430, murder_actor_id='No.05')
    ts.case_evidence_items.append(EvidenceItem(name='knife', found_by='player'))
    d = ts.to_dict()
    ts2 = TrialState.from_dict(d)
    assert ts2.timer_start == 430
    assert ts2.murder_actor_id == 'No.05'
    assert len(ts2.case_evidence_items) == 1
    assert not hasattr(ts2, 'player_has_argued')
    print("TrialState (no closing): OK")

def test_agent_state_with_plan():
    plan = ActionPlan(agent_id='No.01', steps=[
        ActionStep(action_type='MOVE', target_location='Lobby', duration=10)
    ])
    ast = AgentState(agent_id='No.01', name='Test',
                     investigation_result=['found clue'],
                     current_plan=plan)
    d = ast.to_dict()
    ast2 = AgentState.from_dict(d)
    assert ast2.investigation_result == ['found clue']
    assert ast2.current_plan is not None
    print("AgentState with plan: OK")

def test_backward_compat():
    old_ts = {'active': True, 'phase': 'investigation', 'victim_id': 'No.03',
              'case_evidence': [], 'statements': [], 'votes': {},
              'defendant_id': None, 'executed_id': None, 'turn_count': 0,
              'player_has_argued': True}
    ts = TrialState.from_dict(old_ts)
    assert ts.timer_start == 0
    assert ts.murder_actor_id == ''
    print("Backward compat: OK")

if __name__ == '__main__':
    test_intent_types()
    test_plan_data_structures()
    test_conflict_detection()
    test_time_string()
    test_trial_state_no_closing()
    test_agent_state_with_plan()
    test_backward_compat()
    print("\n=== Step 2 ALL TESTS PASSED ===")
