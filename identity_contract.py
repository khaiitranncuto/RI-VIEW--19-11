"""Scene-owned identity evidence, distinct from characters merely mentioned."""
import copy
import hashlib
import json
import re

VERSION = 1


def name_in_text(name, text):
    """Match complete names, excluding common Vietnamese homographs."""
    name, text = str(name or '').strip(), str(text or '')
    if not name:
        return False
    for match in re.finditer(r'(?<!\w)' + re.escape(name) + r'(?!\w)', text, re.I):
        before, after = text[:match.start()], text[match.end():]
        if name.casefold() == 'gian' and (
                re.search(r'(?:thời|không|trung|thế|nhân|dân|dối)\s+$', before, re.I)
                or re.match(r'\s+(?:khổ|nan|truân|lao|dối|xảo|trá|ác|tham)\b', after, re.I)):
            continue
        if name.casefold() == 'nam' and re.search(r'(?:Việt|phía|miền|hướng)\s+$', before, re.I):
            continue
        return True
    return False


def names(character):
    aliases = character.get('aliases') or []
    values = [character.get('name'), *(aliases if isinstance(aliases, list) else [aliases])]
    if not character.get('name'):
        values.append(character.get('display_name') or character.get('neutral_alias'))
    return list(dict.fromkeys(str(v).strip() for v in values if str(v or '').strip()))


def scene_identity_contract(event, characters):
    """Only current-event facts/speech establish permission, never neighbor summaries."""
    people = [c for c in characters or [] if isinstance(c, dict)]
    ids = {str(cid).upper() for cid in event.get('characters') or []}
    facts = [f for f in event.get('observed_facts') or [] if isinstance(f, dict)
             and f.get('status', 'confirmed') == 'confirmed']
    ids.update(str(cid).upper() for f in facts for cid in f.get('canonical_actor_ids') or [])
    visual_text = ' '.join(str(f.get('text') or '') for f in facts
                           if f.get('evidence_kind', 'visual') == 'visual')
    if not facts:
        # Legacy plans predate structured facts; use this event, never its neighbors.
        visual_text = ' '.join(str(event.get(k) or '') for k in ('event', 'visual_detail', 'narration_focus'))
    speech = ' '.join([str(event.get('spoken_text') or ''),
                       *(str(f.get('spoken_text') or '') for f in facts)])
    from character_identity import dialogue_name_mentions
    speech_names = dialogue_name_mentions(speech, [n for c in people for n in names(c)])
    visible, mentioned, roster = [], [], []
    for c in people:
        labels = names(c)
        cid = str(c.get('id') or '').upper()
        in_view = cid in ids or any(name_in_text(n, visual_text) for n in labels)
        in_speech = any(name_in_text(n, speech) or n in speech_names for n in labels)
        if in_view:
            visible.extend(labels)
        if in_speech:
            mentioned.extend(labels)
        if in_view or in_speech:
            roster.append({k: copy.deepcopy(c[k]) for k in (
                'id', 'name', 'display_name', 'neutral_alias', 'name_status',
                'identity_group', 'entity_kind', 'naming_basis', 'relationship_evidence') if k in c})
    return dict(version=VERSION, visible_names=sorted(set(visible)),
                mentioned_names=sorted(set(mentioned)), roster=roster,
                policy='visible_action_requires_visual_fact; offscreen_mention_requires_speech_or_fact',
                evidence=[{k: copy.deepcopy(f[k]) for k in (
                    'fact_id', 'text', 'shot_ids', 'canonical_actor_ids', 'spoken_text') if k in f}
                    for f in facts])


def character_issues(scene, characters):
    contract = scene.get('identity_contract') or {}
    visible = contract.get('visible_names', scene.get('allowed_character_names') or [])
    mentioned = contract.get('mentioned_names', [])
    permitted = {str(n).casefold() for n in [*visible, *mentioned]}
    if not permitted and not contract:
        return []  # Old, unscoped payloads are checked by the factual verifier.
    unexpected = list(dict.fromkeys(n for c in characters or [] for n in names(c)
        if n.casefold() not in permitted and name_in_text(n, scene.get('tts', ''))))
    if not unexpected:
        return []
    return [dict(scene_id=scene.get('scene_id'), unexpected_names=unexpected,
                 allowed_names=sorted(permitted), visible_names=visible,
                 mentioned_names=mentioned, tts=scene.get('tts', ''),
                 identity_evidence=contract.get('evidence', []),
                 version=audit_signature(scene),
                 locked_visual_shots=copy.deepcopy(scene.get('locked_visual_shots') or []),
                 reason='name_not_supported_by_current_scene_evidence')]


def audit_signature(scene, source_identity=None, visual_signature=None):
    sid = scene.get('scene_id') or re.sub(r'^E(?=\d+$)', 'S', str(scene.get('event_id') or ''))
    data = ['narration_audit_v2', sid,
            scene.get('tts'), scene.get('observed_facts'), scene.get('transition_contract'),
            scene.get('identity_contract') or {}, scene.get('allowed_character_names') or [], source_identity]
    if visual_signature is not None:
        data += ['video', visual_signature]
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def conflicting_verdict(scene, verdict):
    """Flag contradictions for review; a string match never grants a pass."""
    if not verdict or verdict.get('faithful') is not False:
        return False
    reason = str(verdict.get('reason') or '')
    if not re.search(r'không (?:có|được|xuất hiện)|not (?:in|supported|present)|absent|missing from', reason, re.I):
        return False
    facts = ' '.join(str(f.get('text') or '') for f in scene.get('observed_facts') or [])
    claims = re.findall(r'["“‘\(]([^"”’\)]+)["”’\)]', reason)
    return any(len(claim.split()) >= 2 and name_in_text(claim.strip(), facts) for claim in claims)
