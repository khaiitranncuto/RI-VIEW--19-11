"""Backend-owned writer slots and one shared per-unit repair allowance."""
import json


def slots(events):
    result = {}
    for event in events:
        units = event.get('sentence_slots') or []
        if len(units) != int(event['sentence_quota']):
            raise ValueError('WRITER_PLAN_QUOTA_INVALID:' + event['event_id'])
        facts = {f['fact_id'] for f in event.get('observed_facts') or []}
        for unit in units:
            uid = unit['unit_id']
            if uid in result or not unit.get('fact_ids') or not set(unit['fact_ids']) <= facts:
                raise ValueError('WRITER_PLAN_EVIDENCE_INVALID:' + uid)
            if not unit.get('visual_ids') or not unit.get('shot_ids'):
                raise ValueError('WRITER_PLAN_VISUAL_INVALID:' + uid)
            result[uid] = event['event_id']
        from narration_units import validate_narration_unit_order
        validate_narration_unit_order(event)
    return result


def schema(events):
    keys = slots(events)
    return {'type': 'object', 'properties': {key: {'type': 'string'} for key in keys},
            'required': list(keys), 'additionalProperties': False}


def prompt(original, events):
    return (original + '\nOUTPUT CONTRACT OVERRIDE: Return only a JSON object mapping '
        'each required unit_id key to its one complete narration sentence. '
        'Do not return sentences arrays or event_id fields. All keys are mandatory; '
        'never merge, add or remove units. Backend owns identities and evidence. '
        'Required keys in story order: ' + json.dumps(list(slots(events))))


def decode(raw, events):
    from recap_visual_media import parse_writing_response
    value = parse_writing_response(raw)
    expected = slots(events)
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError('NARRATION_UNIT_KEYS_INVALID')
    if any(not isinstance(value[key], str) or not value[key].strip() for key in expected):
        raise ValueError('NARRATION_UNIT_TEXT_EMPTY')
    return json.dumps({'sentences': [dict(event_id=eid, unit_id=uid, text=value[uid])
        for uid, eid in expected.items()]}, ensure_ascii=False)


def reserve(events, counts, maximum=3):
    """Count all draft/repair layers against the same unit allowance."""
    keys = list(slots(events))
    exhausted = [key for key in keys if counts.get(key, 0) >= maximum]
    if exhausted:
        raise ValueError('WRITER_REPAIR_BUDGET_EXHAUSTED:' + ','.join(exhausted))
    for key in keys:
        counts[key] = counts.get(key, 0) + 1
