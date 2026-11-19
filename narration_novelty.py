"""Conservative evidence deduplication before quota allocation, and prose guards.

Semantic paraphrases are judged by the existing model verifier. Local checks
only collapse identical facts in one continuous situation or shared footage.
They never invent replacement footage or reduce the requested sentence count.
"""
import copy
import re
import unicodedata


VERSION = 1


def normalized(text):
    return ' '.join(re.findall(r'\w+', unicodedata.normalize('NFC', str(text)).casefold()))


def deduplicate_plan(plan, duplicate_pairs=None):
    from evidence_writer import supported_facts
    from transition_contract import confirmed_time_change
    result = copy.deepcopy(plan)
    reviewed = dict(duplicate_pairs or [])
    removed, previous, seen = [], None, {}
    for group in result.get('events_by_part') or []:
        kept = []
        for event in group:
            context = event.get('scene_context') or {}
            prior = (previous or {}).get('scene_context') or {}
            same_run = bool(previous and event.get('situation_id')
                and event.get('situation_id') == previous.get('situation_id')
                and normalized(context.get('location', '')) == normalized(prior.get('location', ''))
                and not confirmed_time_change(context.get('time_context'), prior.get('time_context'))
                and 0 <= float(event.get('start_seconds', 0)) - float(previous.get('end_seconds', 0)) <= 30)
            if not same_run:
                seen = {}
            facts = []
            for fact in supported_facts(event):
                if fact['fact_id'] in reviewed:
                    removed.append(dict(event_id=event['event_id'], fact_id=fact['fact_id'],
                                        retained_fact_id=reviewed[fact['fact_id']], method='semantic_review'))
                    continue
                key = (normalized(fact['text']), fact.get('evidence_kind', 'visual'),
                       tuple(sorted(fact.get('canonical_actor_ids') or fact.get('actor_ids') or [])))
                old = seen.get(key)
                shared_shots = bool(old and set(fact.get('shot_ids') or []) & old['shots'])
                repeated_state = bool(old and event.get('repeat_group')
                    and event.get('repeat_group') == old['repeat_group'])
                if old and (shared_shots or repeated_state):
                    removed.append(dict(event_id=event['event_id'], fact_id=fact['fact_id'],
                                        retained_fact_id=old['fact_id']))
                else:
                    seen[key] = dict(fact_id=fact['fact_id'], shots=set(fact.get('shot_ids') or []),
                                     repeat_group=event.get('repeat_group'))
                    facts.append(fact)
            previous = event
            if not facts:
                continue
            event['observed_facts'] = facts
            event['planned_fact_ids'] = [f['fact_id'] for f in facts]
            # Remove dangling source ownership, retaining footage for kept facts.
            ids = set(event['planned_fact_ids'])
            shots = {s for f in facts for s in f.get('shot_ids') or []}
            sources = []
            for source in event.get('visual_sources') or []:
                owned = set(source.get('shot_ids') or [source.get('shot_id')])
                if not owned & shots:
                    continue
                source = copy.deepcopy(source)
                if 'fact_ids' in source:
                    source['fact_ids'] = [fid for fid in source['fact_ids'] if fid in ids]
                sources.append(source)
            event['visual_sources'] = sources
            for key in ('sentence_slots', 'narration_unit_version', 'sentence_quota'):
                event.pop(key, None)
            kept.append(event)
        group[:] = kept
    rows = [e for g in result.get('events_by_part') or [] for e in g]
    owners = {f['fact_id']: e['event_id'] for e in rows for f in e['observed_facts']}
    retained_events = {e['event_id'] for e in rows}
    redirects = {r['event_id']: owners[r['retained_fact_id']] for r in removed
                 if r['event_id'] not in retained_events and r['retained_fact_id'] in owners}
    for event in rows:
        dependencies = event.get('depends_on') or []
        if isinstance(dependencies, str):
            dependencies = [dependencies]
        event['depends_on'] = list(dict.fromkeys(redirects.get(d, d) for d in dependencies
            if redirects.get(d, d) != event['event_id']))
        event['event'] = event['narration_focus'] = ' '.join(f['text'] for f in event['observed_facts'])
    contract = result.setdefault('scene_contract', {})
    contract.update(scene_count=len(rows), part_scene_counts=[len(g) for g in result['events_by_part']])
    result['narration_novelty'] = dict(version=VERSION, removed_facts=removed,
        remaining_fact_count=sum(len(e['observed_facts']) for e in rows))
    return result


def review_plan_novelty(plan, generate):
    """Review complete facts before allocating count, never delete partial repeats.

    Source windows and identity are validated locally; judging paraphrases is
    delegated to the configured verifier, with no access to arbitrary footage.
    """
    from evidence_writer import supported_facts
    from transition_contract import confirmed_time_change
    import json
    records = []
    for group in plan.get('events_by_part') or []:
        for event in group:
            for fact in supported_facts(event):
                records.append(dict(fact_id=fact['fact_id'], text=fact['text'],
                    actor_ids=fact.get('canonical_actor_ids') or fact.get('actor_ids') or [],
                    evidence_kind=fact.get('evidence_kind', 'visual'),
                    event_id=event['event_id'], context=event.get('scene_context') or {},
                    start=float(event.get('start_seconds', 0)), end=float(event.get('end_seconds', 0))))
    known = {r['fact_id']: (i, r) for i, r in enumerate(records)}
    pairs = {}
    for offset in range(0, len(records), 48):
        current = records[offset:offset + 48]
        cards = records[max(0, offset - 12):offset] + current
        if len(cards) < 2:
            continue
        prompt = (
            'Kiem tra TRUNG DIEN BIEN truoc khi phan bo so cau. Chi danh dau mot fact '
            'neu TOAN BO thong tin cua no da duoc fact truoc ke, cung mot lan xay ra. '
            'Khac chu nhung cung y van la trung. Cung hanh dong nhung lan khac, khac ngay '
            'hoac co ket qua/chi tiet moi thi KHONG xoa. Trung mot phan thi giu nguyen '
            'de writer giu chi tiet moi. Khong xoa mat xich nhan qua hay nguoi tham gia moi. '
            'Neu khong chac thi giu. Chi tra duplicates voi fact_id, retained_fact_id, '
            'same_occurrence=true, adds_information=false. retained_fact_id phai xuat hien '
            'TRUOC fact_id trong danh sach. Chi xet fact_id thuoc target_ids.\n'
            + json.dumps(dict(target_ids=[r['fact_id'] for r in current], facts=cards), ensure_ascii=False))
        response = generate(prompt)
        if isinstance(response, str):
            from recap_visual_media import parse_writing_response
            response = parse_writing_response(response)
        if not isinstance(response, dict) or not isinstance(response.get('duplicates'), list):
            raise ValueError('NARRATION_NOVELTY_REVIEW_INVALID')
        targets = {r['fact_id'] for r in current}
        available = {r['fact_id'] for r in cards}
        for pair in response['duplicates']:
            if not isinstance(pair, dict):
                raise ValueError('NARRATION_NOVELTY_REVIEW_INVALID')
            fid, retained = pair.get('fact_id'), pair.get('retained_fact_id')
            if (fid not in targets or retained not in available or fid == retained
                    or pair.get('same_occurrence') is not True or pair.get('adds_information') is not False):
                continue
            i, right = known[fid]
            j, left = known[retained]
            a, b = left['context'], right['context']
            if (j >= i or right['start'] - left['end'] > 60
                    or left['evidence_kind'] != right['evidence_kind']
                    or sorted(left['actor_ids']) != sorted(right['actor_ids'])
                    or (a.get('location') and b.get('location')
                        and normalized(a['location']) != normalized(b['location']))
                    or confirmed_time_change(a.get('time_context'), b.get('time_context'))):
                continue
            while retained in pairs:
                retained = pairs[retained]
            pairs[fid] = retained
    return deduplicate_plan(plan, pairs.items())


def duplicate_sentences(scenes):
    """Find verbatim repeats locally; distant recurring actions need semantics."""
    from narrative_contract import sentence_texts
    issues, recent = [], []
    for scene in scenes:
        sid = scene.get('scene_id') or scene.get('event_id')
        facts = scene.get('observed_facts') or []
        fact_ids = {f['fact_id'] for f in facts if f.get('fact_id')}
        shots = {shot for f in facts for shot in f.get('shot_ids') or []}
        current = []
        for index, text in enumerate(sentence_texts(scene.get('tts') or '')):
            key = normalized(text)
            match = next((r for r in recent + current if r['key'] == key
                and (r['scene_id'] == sid or r['facts'] & fact_ids or r['shots'] & shots)), None)
            if key and match:
                issues.append(dict(code='DUPLICATE_NARRATION', scene_id=sid,
                    sentence_index=index, previous_scene_id=match['scene_id'], text=text))
            current.append(dict(key=key, scene_id=sid, facts=fact_ids, shots=shots))
        recent = (recent + current)[-12:]
    return issues


def novelty_contexts(scenes):
    """Give the verifier prose across batch boundaries, not just one sentence."""
    result = {}
    from recap_pipeline import REPETITION_STOPWORDS
    def tokens(scene):
        return set(normalized(scene.get('tts') or '').split()) - REPETITION_STOPWORDS
    for i, scene in enumerate(scenes):
        current = tokens(scene)
        related = []
        for j, older in enumerate(scenes[:max(0, i - 3)]):
            other = tokens(older)
            score = len(current & other) / max(1, len(current | other))
            if score >= .45:
                related.append((score, j))
        indices = sorted({j for _, j in sorted(related, reverse=True)[:3]}
                         | set(range(max(0, i - 3), i)))
        sid = scene.get('scene_id') or scene.get('event_id')
        result[sid] = [dict(scene_id=scenes[j].get('scene_id') or re.sub(r'^E(?=\d+$)', 'S', str(scenes[j].get('event_id') or '')),
            tts=scenes[j].get('tts', ''), observed_facts=scenes[j].get('observed_facts') or [])
            for j in indices]
    return result


def novelty_signature(signature, context):
    import hashlib
    import json
    return hashlib.sha256(json.dumps([signature, VERSION, context],
        ensure_ascii=False, sort_keys=True).encode()).hexdigest()
