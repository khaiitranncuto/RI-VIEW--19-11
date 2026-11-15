"""Backend-owned narration units: identity/count independent of punctuation."""
import copy
import json
import math

from semantic_visuals import visual_catalog, timecode, seconds


def _source_window(source):
    start = source.get('start_seconds')
    end = source.get('end_seconds')
    if start is None:
        start = seconds(source.get('start'))
    if end is None:
        end = seconds(source.get('end'))
    start, end = float(start), float(end)
    if not math.isfinite(start + end) or not 0 <= start < end:
        raise ValueError('NARRATION_UNIT_SOURCE_WINDOW_INVALID')
    return start, end


def _shot_ids(row):
    return set(row.get('shot_ids') or ([row['shot_id']] if row.get('shot_id') else []))


def _fact_sources(fact_id, fact, sources):
    """Prefer explicit fact ownership; shot overlap is only a legacy fallback."""
    explicit = [source for source in sources if fact_id in (source.get('fact_ids') or [])]
    if explicit:
        return explicit
    fact_shots = set(fact.get('shot_ids') or [])
    return [source for source in sources if fact_shots & _shot_ids(source)]


def _fact_timeline(facts, sources, event_id):
    """Resolve fact order from source shots, independent of model/list order."""
    rows = []
    for original_index, (fact_id, fact) in enumerate(facts.items()):
        fact_shots = set(fact.get('shot_ids') or [])
        owners = _fact_sources(fact_id, fact, sources)
        if not owners:
            raise ValueError(f'NARRATION_UNIT_FACT_SOURCE_MISSING:{event_id}:{fact_id}')
        windows = [_source_window(source) for source in owners]
        rows.append((min(a for a, _ in windows), max(b for _, b in windows),
                     original_index, fact_id, fact_shots))
    return sorted(rows, key=lambda row: (row[0], row[1], row[2], row[3]))


def validate_narration_unit_order(event):
    previous_start, previous_end, previous_visuals = -1.0, -1.0, set()
    for slot in event.get('sentence_slots') or []:
        start = float(slot.get('source_start', -1))
        end = float(slot.get('source_end', -1))
        visuals = set(slot.get('visual_ids') or [])
        shared = bool(previous_visuals & visuals)
        if (not math.isfinite(start + end) or not 0 <= start < end
                or start < previous_start - .001
                or (start < previous_end - .001 and not shared)):
            raise ValueError(f'NARRATION_UNIT_SOURCE_ORDER_INVALID:{event.get("event_id")}:'
                             f'{slot.get("unit_id")}; previous_start={previous_start}; '
                             f'previous_end={previous_end}; start={start}; shared={shared}')
        previous_start, previous_end, previous_visuals = start, end, visuals
    return True


def _unit_visuals(ids, facts, visuals):
    """Return only visuals actually owned by the unit's facts."""
    selected = {}
    for fact_id in ids:
        explicit = [v for v in visuals if fact_id in (v.get('fact_ids') or [])]
        owners = explicit or [v for v in visuals
                              if set(facts[fact_id].get('shot_ids') or []) & _shot_ids(v)]
        for visual in owners:
            selected[visual['visual_id']] = visual
    return sorted(selected.values(), key=lambda v: (v['start_seconds'], v['end_seconds']))


def plan_narration_units(plan):
    from evidence_writer import supported_facts
    result = copy.deepcopy(plan)
    for group in result['events_by_part']:
        for event in group:
            facts = {f['fact_id']: f for f in supported_facts(event)}
            sources = []
            for raw_source in event['visual_sources']:
                start, end = _source_window(raw_source)
                sources.append(dict(raw_source, start_seconds=start, end_seconds=end,
                    start=raw_source.get('start') or timecode(start),
                    end=raw_source.get('end') or timecode(end)))
            visuals = sorted(visual_catalog(sources), key=lambda v: v['start_seconds'])
            if not visuals:
                raise ValueError('NARRATION_UNIT_VISUALS_MISSING:' + event['event_id'])
            slots, quota = [], int(event['sentence_quota'])
            fact_timeline = _fact_timeline(facts, sources, event['event_id'])
            ordered_facts = [row[3] for row in fact_timeline]
            fact_windows = {row[3]: (row[0], row[1], row[4]) for row in fact_timeline}
            distinct_policy = result.get('evidence_capacity_policy') == 'distinct_facts'
            unit_fact_ids = ([ordered_facts[len(ordered_facts) * i // quota:
                               len(ordered_facts) * (i + 1) // quota]
                              for i in range(quota)] if distinct_policy else None)
            unit_starts = ([min(fact_windows[fid][0] for fid in ids)
                            for ids in unit_fact_ids] if distinct_policy else None)
            for i in range(quota):
                a = len(visuals) * i // quota
                b = len(visuals) * (i + 1) // quota
                chosen = visuals[a:max(a + 1, b)]
                ids = list(dict.fromkeys(fid for v in chosen for fid in v['fact_ids'] if fid in facts))
                if distinct_policy:
                    ids = unit_fact_ids[i]
                    start = unit_starts[i]
                    next_start = unit_starts[i + 1] if i + 1 < quota else float('inf')
                    owned = _unit_visuals(ids, facts, visuals)
                    # Allocate the complete event in one forward pass. A fact
                    # may own several shots, but a unit cannot consume a shot
                    # whose start belongs to the following unit. Equal starts
                    # are allowed only for visuals explicitly supporting each
                    # unit; they never open the interval to the rest of event.
                    chosen = [v for v in owned if v['start_seconds'] >= start - .001
                              and (not math.isfinite(next_start)
                                   or v['start_seconds'] < next_start - .001
                                   or (abs(next_start - start) <= .001
                                       and abs(v['start_seconds'] - start) <= .001))]
                if not ids:
                    raise ValueError('NARRATION_UNIT_FACTS_MISSING:' + event['event_id'])
                if not chosen:
                    raise ValueError('NARRATION_UNIT_FACT_VISUAL_MISSING:' + event['event_id']
                                     + ':' + ','.join(ids))
                chosen = sorted(chosen, key=lambda v: (v['start_seconds'], v['end_seconds']))
                source_start = chosen[0]['start_seconds']
                source_end = max(v['end_seconds'] for v in chosen)
                event_word_target = max(quota, int(event.get('tts_target_words') or quota * 20))
                unit_word_target = (
                    event_word_target * (i + 1) // quota
                    - event_word_target * i // quota
                )
                slots.append(dict(unit_id=f'{event["event_id"]}_U{i + 1:03d}',
                    slot_id=f'{event["event_id"]}_C{i + 1:03d}', fact_ids=ids,
                    shot_ids=list(dict.fromkeys(s for v in chosen for s in v['shot_ids'])),
                    visual_ids=[v['visual_id'] for v in chosen],
                    source_start=source_start, source_end=source_end,
                    target_words=unit_word_target,
                    focus=' '.join(facts[fid]['text'] for fid in ids)))
            event.update(sentence_slots=slots, narration_unit_version=1, visual_sources=sources)
            validate_narration_unit_order(event)
    result['narration_unit_version'] = 1
    return result


def unit_schema(events):
    return {'type': 'object', 'properties': {'sentences': {'type': 'array', 'items': {
        'type': 'object', 'properties': {'event_id': {'type': 'string'},
        'unit_id': {'type': 'string'}, 'text': {'type': 'string'}},
        'required': ['event_id', 'unit_id', 'text']}}}, 'required': ['sentences']}


def unit_prompt(events, context, previous=None, error=None):
    from evidence_writer import VIETNAMESE_WRITER_RULE, paragraph_card
    from character_identity import render_identity_context
    people = context.get('characters') or []
    cards = []
    for event in events:
        card = paragraph_card(event)
        cards.append(dict(event_id=event['event_id'],
            role=card['narrative_role'], allowed_names=card['allowed_names'],
            scene_context=card['scene_context'],
            facts=[dict(f, text=render_identity_context(f['text'], people)) for f in card['facts']],
            units=[dict(unit_id=u['unit_id'], fact_ids=u['fact_ids'],
                        source_start=u.get('source_start'), source_end=u.get('source_end'),
                        target_words=u.get('target_words', 20),
                        **({'transition_contract': u['transition_contract']}
                           if u.get('transition_contract') else {}))
                   for u in event['sentence_slots']],
            **({'transcript_context_only': card['transcript_context_only']}
               if card.get('transcript_context_only') else {})))
    packet = dict(style=context.get('style') or '', requirements=context.get('custom_prompt') or '',
        story=[render_identity_context(str(s)[:600], people)
               for s in context.get('all_part_summaries') or []],
        before=[str(s.get('tts') or '')[-600:]
                for s in (context.get('previous_part_tail') or [])[-2:]],
        after=[render_identity_context(str(s.get('event') or '')[:600], people)
               for s in (context.get('next_batch_context') or [])[:2]], events=cards)
    if error:
        wanted = {e['event_id'] for e in events}
        packet['repair'] = dict(error=str(error), previous=[dict(event_id=r['event_id'],
            **({'units': [dict(unit_id=u.get('unit_id'), text=u.get('text'))
                         for u in r['narration_units']]} if r.get('narration_units') else
               {'text': r.get('paragraph') or r.get('tts') or ''}))
            for r in (previous or {}).get('scenes') or [] if r.get('event_id') in wanted])
    return (VIETNAMESE_WRITER_RULE +
        'DON VI LOI KE CO ID; MOI ID BAT BUOC DUNG MOT CAU NGU PHAP. '
        'Đọc toàn cụm, viết thành mạch recap liền nhau rồi trả từng unit theo thứ tự. '
        'Mỗi unit_id có đúng một text, text đó phải là ĐÚNG MỘT câu ngữ pháp kết thúc bằng dấu câu; '
        'một câu có thể gồm nhiều mệnh đề và dùng một hoặc nhiều shot đã khóa. '
        'Viết gần đúng target_words của unit để toàn bài đạt thời lượng; không rút thành câu cụt. '
        'Chỉ kể chi tiết trong facts được giao cho unit; nhiều unit dùng cùng fact '
        'phải kể các chi tiết khác nhau có thật, không lặp ý để đủ số lượng. '
        'Giữ đúng nhân vật, hành động và trình tự source_order; không tự thêm '
        'kết quả, nội tâm, quan hệ nhân quả hay suy đoán. scene_context, story và '
        'transcript chỉ giúp hiểu mạch, không chứng minh hành động đang thấy. '
        'Chỉ dùng lời người kể, không trích thoại hay sao chép Whisper; chỉ kể '
        'gián tiếp ý nghĩa lời nói khi fact dialogue có nội dung rõ ràng. '
        'Nối đoạn với before/after tự nhiên, không viết lại chúng; giữ tên nhất quán. '
        'transition_contract khóa QUAN HỆ NGỮ NGHĨA ở ranh giới sự kiện, không khóa câu chữ. '
        'Hãy diễn đạt tự nhiên và đa dạng theo ngữ cảnh (có thể dùng cấu trúc như sau một hành động, '
        'khi một việc kết thúc, chuẩn bị cho hành động, phát hiện rồi phản ứng, vượt trở ngại, '
        'hoặc giới thiệu lại chủ thể). Theo dõi các câu ngay trước để tránh lặp cùng một từ nối; '
        'nhưng tuyệt đối không thêm quan hệ thời gian, '
        'nhân quả, song song hay quay lại ngoài relation và các anchor đã cho. '
        'Với neutral_reintroduction, chỉ giới thiệu lại chủ thể/địa điểm hiện tại đã xác nhận; '
        'không dùng từ ngụ ý trước-sau hoặc nguyên nhân-kết quả. continuation không bắt buộc có từ nối. '
        'Phần ending kể ngắn gọn kết quả được chứng minh, không thêm tổng kết. '
        'Trả đúng ID theo units, không thêm bớt. Backend kiểm số lượng và gắn hình. '
        'Chỉ trả JSON {"sentences":[{"event_id":"E0001","unit_id":"E0001_U001",'
        '"text":"Lời kể."}]}.\n'
        + json.dumps(packet, ensure_ascii=False, separators=(',', ':')))



def unit_response(payload, events):
    from narrative_contract import sentences, words
    rows = payload.get('sentences') if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError('NARRATION_UNIT_SCHEMA_INVALID')
    known = {e['event_id']: e for e in events}
    groups = {}
    for row in rows:
        if not isinstance(row, dict) or row.get('event_id') not in known:
            raise ValueError('NARRATION_UNIT_EVENT_INVALID')
        groups.setdefault(row['event_id'], []).append(row)
    result = []
    for eid, event in known.items():
        units = groups.get(eid, [])
        expected = [u['unit_id'] for u in event['sentence_slots']]
        error = None
        if [u.get('unit_id') for u in units] != expected:
            error = 'NARRATION_UNIT_IDS_INVALID:' + eid + '; expected=' + str(expected)
        elif any(not isinstance(u.get('text'), str) or not u['text'].strip() for u in units):
            error = 'NARRATION_UNIT_TEXT_EMPTY:' + eid
        elif any(len(sentences(u['text'])) != 1 for u in units):
            error = 'NARRATION_UNIT_ONE_SENTENCE_REQUIRED:' + eid
        target_words = sum(int(slot.get('target_words') or 20)
                           for slot in event.get('sentence_slots') or [])
        actual_words = sum(words(unit['text']) for unit in units
                           if isinstance(unit.get('text'), str))
        tolerance = max(2, round(target_words * 0.03))
        word_budget_warning = None
        if (not error and
                not target_words - tolerance <= actual_words <= target_words + tolerance):
            # Word budgets guide one targeted rewrite and candidate ranking;
            # they are never a structural reason to discard a valid script.
            word_budget_warning = {
                'target_words': target_words,
                'minimum_words': target_words - tolerance,
                'maximum_words': target_words + tolerance,
                'actual_words': actual_words,
                'distance': max(target_words - tolerance - actual_words,
                                actual_words - target_words - tolerance, 0),
            }
        facts = {f['fact_id']: f for f in event['observed_facts']}
        proofs = []
        for slot in event['sentence_slots']:
            kinds = {facts[fid].get('evidence_kind', 'visual') for fid in slot['fact_ids']}
            if len(kinds) != 1:
                error = 'NARRATION_UNIT_MIXED_SOURCE:' + slot['unit_id']
            proofs.append(dict(fact_ids=slot['fact_ids'], evidence_kind=next(iter(kinds))))
        result.append(dict(event_id=eid, paragraph=' '.join(u.get('text', '') for u in units if isinstance(u.get('text'), str)),
            narration_units=copy.deepcopy(units), sentence_evidence=proofs,
            **({'word_budget_warning': word_budget_warning} if word_budget_warning else {}),
            **({'format_error': error} if error else {})))
    return {'scenes': result}
