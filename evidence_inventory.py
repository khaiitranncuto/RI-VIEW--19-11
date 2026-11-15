"""Read-only inventory and adaptive review windows for source observations."""
import math


def inventory(chunks):
    events = [e for c in chunks for e in c.get('events') or []]
    facts = [f for e in events for f in e.get('grounded_facts') or []]
    return dict(events=len(events), facts=len(facts),
                source_shots=len({s for f in facts for s in f.get('shot_ids') or []}))


def detail_windows(chunks, duration, target, limit=None, seconds=60, reviewed=None):
    """Return unreviewed source intervals ordered from sparsest to richest.

    The primary 2-FPS pass is independent from recap duration.  This scheduler
    is only a recovery mechanism when that pass compressed a long interval too
    aggressively.  It may cover the whole film; it never fabricates facts.
    """
    if inventory(chunks)['facts'] >= target:
        return []
    reviewed = {
        (round(float(row[0]), 3), round(float(row[1]), 3))
        for row in (reviewed or []) if isinstance(row, (list, tuple)) and len(row) == 2
    }
    candidates = []
    for start in range(0, math.ceil(duration), seconds):
        end = min(duration, start + seconds)
        if end - start < 5:
            continue
        key = (round(float(start), 3), round(float(end), 3))
        if key in reviewed:
            continue
        events = [e for c in chunks for e in c.get('events') or []
                  if float(e.get('start_seconds', 0)) < end
                  and float(e.get('end_seconds', 0)) > start]
        facts = {f.get('fact_id') for e in events for f in e.get('grounded_facts') or []}
        candidates.append(dict(start_seconds=start, end_seconds=end,
                               known_fact_count=len(facts),
                               reason=('sparse_story_details' if events
                                       else 'missing_story_observations')))
    ordered = sorted(candidates, key=lambda w: (w['known_fact_count'], w['start_seconds']))
    return ordered if limit is None else ordered[:max(0, int(limit))]
