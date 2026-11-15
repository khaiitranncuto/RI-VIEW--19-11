"""Evidence-backed semantic contracts for narration boundaries.

The backend decides what relationship is safe to express.  The writer remains
free to choose natural Vietnamese wording; no connector phrase is whitelisted.
"""
import copy
import re


VERSION = 1
_EXPLICIT = {
    'continuation': 'continuation',
    'time_jump': 'time_jump',
    'flashback': 'time_jump',
    'flashforward': 'time_jump',
    'parallel': 'parallel',
    'return': 'return',
    'cause': 'consequence',
    'consequence': 'consequence',
    'preparation': 'preparation',
    'completion': 'completion',
    'discovery_reaction': 'discovery_reaction',
    'obstacle_solution': 'obstacle_solution',
    'location_change': 'location_change',
}
_GENERIC_CONTEXT = {'', 'unknown', 'khong ro', 'không rõ', 'none', 'n/a'}


def _text(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _known(value):
    value = _text(value)
    return value if value.casefold() not in _GENERIC_CONTEXT else ''


def _characters(event):
    values = event.get('characters') or event.get('character_ids') or []
    if isinstance(values, str):
        values = [values]
    return sorted({_text(value) for value in values if _text(value)})


def _anchor(event, fields):
    for field in fields:
        value = _known(event.get(field))
        if value:
            return value
    return ''


def _contract(previous, current, first=False):
    current_context = current.get('scene_context') or {}
    if first:
        return {
            'version': VERSION, 'relation': 'opening', 'requires_bridge': False,
            'confidence': 1.0, 'current_event_id': current.get('event_id'),
            'current_anchor': _anchor(current, ('event', 'narration_focus', 'action')),
            'evidence_basis': ['story_opening'],
        }

    previous_context = previous.get('scene_context') or {}
    bridge = current.get('bridge_from_previous') or {}
    bridge_relation = (
        _text(bridge.get('relation')).casefold() if isinstance(bridge, dict) else ''
    )
    bridge_facts = (
        bridge.get('facts') or bridge.get('shot_ids') or []
        if isinstance(bridge, dict) else []
    )
    raw_relation = _text(current.get('temporal_relation')).casefold()
    relation = _EXPLICIT.get(raw_relation)
    basis = []
    confidence = 0.55

    if bridge_relation in _EXPLICIT and bridge_facts:
        relation = _EXPLICIT[bridge_relation]
        basis.append('verified_bridge_from_previous')
        confidence = 0.94

    depends_on = current.get('depends_on') or []
    if isinstance(depends_on, str):
        depends_on = [depends_on]
    if previous.get('event_id') and previous.get('event_id') in depends_on:
        relation = 'consequence'
        basis.append('explicit_event_dependency')
        confidence = 0.92

    if relation and relation != 'consequence' and 'verified_bridge_from_previous' not in basis:
        basis.append('planner_temporal_relation')
        confidence = 0.9 if relation != 'continuation' else 0.75

    previous_location = _known(previous_context.get('location'))
    current_location = _known(current_context.get('location'))
    previous_time = _known(previous_context.get('time_context'))
    current_time = _known(current_context.get('time_context'))
    same_situation = bool(_known(previous.get('situation_id')) and
                          _known(previous.get('situation_id')) == _known(current.get('situation_id')))
    same_beat = bool(_known(previous.get('story_beat_id')) and
                     _known(previous.get('story_beat_id')) == _known(current.get('story_beat_id')))

    # Confirmed planner relations take precedence.  Context comparisons are
    # only used when the planner did not identify a non-continuation relation.
    if relation in (None, 'continuation'):
        if previous_location and current_location and previous_location.casefold() != current_location.casefold():
            relation, confidence = 'location_change', 0.85
            basis.append('confirmed_location_change')
        elif previous_time and current_time and previous_time.casefold() != current_time.casefold():
            relation, confidence = 'time_jump', 0.82
            basis.append('confirmed_time_context_change')
        elif same_situation or same_beat:
            relation, confidence = 'continuation', 0.8
            basis.append('same_situation' if same_situation else 'same_story_beat')
        elif relation != 'continuation':
            relation = 'neutral_reintroduction'
            basis.append('relationship_unconfirmed')

    previous_ids = _characters(previous)
    current_ids = _characters(current)
    if (relation == 'continuation' and previous_ids and current_ids
            and not set(previous_ids) & set(current_ids) and not (same_situation or same_beat)):
        relation, confidence = 'neutral_reintroduction', 0.65
        basis.append('subject_changed_without_confirmed_link')

    if relation is None:
        relation = 'neutral_reintroduction'
        basis.append('relationship_unconfirmed')

    previous_anchor = _anchor(previous, ('outcome', 'state_after', 'result', 'consequence',
                                         'event', 'narration_focus'))
    current_anchor = _anchor(current, ('state_before', 'cause', 'event', 'narration_focus', 'action'))
    semantic_goals = {
        'continuation': 'continue_same_situation_without_repeating_the_previous_fact',
        'consequence': 'connect_verified_previous_outcome_to_current_action',
        'preparation': 'state_verified_preparation_before_the_supported_action',
        'completion': 'mark_verified_action_completion_before_the_next_state',
        'discovery_reaction': 'connect_verified_discovery_to_observed_reaction',
        'obstacle_solution': 'connect_observed_obstacle_to_verified_solution',
        'parallel': 'switch_to_a_confirmed_parallel_story_line',
        'return': 'return_to_a_previously_confirmed_story_line',
        'time_jump': 'signal_a_confirmed_change_in_time',
        'location_change': 'introduce_the_confirmed_new_location',
        'neutral_reintroduction': 'reintroduce_only_the_confirmed_current_subject_or_place',
    }
    return {
        'version': VERSION,
        'relation': relation,
        'requires_bridge': relation not in ('opening', 'continuation'),
        'confidence': confidence,
        'previous_event_id': previous.get('event_id'),
        'current_event_id': current.get('event_id'),
        'previous_anchor': previous_anchor,
        'current_anchor': current_anchor,
        'previous_characters': previous_ids,
        'current_characters': current_ids,
        'previous_location': previous_location,
        'current_location': current_location,
        'previous_time_context': previous_time,
        'current_time_context': current_time,
        'evidence_basis': list(dict.fromkeys(basis)),
        'semantic_goal': semantic_goals.get(relation, semantic_goals['neutral_reintroduction']),
        'variation_key': f'{relation}:{current.get("event_id") or "unknown"}',
        'forbidden_inferences': [
            'unverified_causality', 'unverified_intention',
            'unverified_simultaneity', 'unverified_action_completion',
        ],
        'wording_policy': ('free_semantic_paraphrase' if relation != 'neutral_reintroduction'
                           else 'neutral_current_anchor_only'),
    }


def apply_transition_contracts(plan):
    """Attach one global, source-ordered boundary contract to every event."""
    result = copy.deepcopy(plan)
    events = [event for group in result.get('events_by_part') or [] for event in group]
    previous = None
    for event in events:
        contract = _contract(previous, event, first=previous is None)
        event['transition_contract'] = contract
        event['transition_contract_version'] = VERSION
        slots = event.get('sentence_slots') or []
        for index, slot in enumerate(slots):
            if index == 0:
                slot['transition_contract'] = copy.deepcopy(contract)
            else:
                slot.pop('transition_contract', None)
        previous = event
    result['transition_contract_version'] = VERSION
    return result
