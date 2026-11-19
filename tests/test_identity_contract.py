import copy
import unittest
from unittest.mock import Mock

from character_identity import render_ids, profile
from identity_contract import (name_in_text, scene_identity_contract, character_issues,
                               audit_signature)
from grounded_pipeline import audit_narrations, preserve_verified_scenes
from evidence_writer import audit_planned_payload
from recap_pipeline import build_part_story_context


PEOPLE = [{'id': 'P01', 'name': 'Nobita'}, {'id': 'P02', 'name': 'Doraemon'},
          {'id': 'P03', 'name': 'Shizuka'}, {'id': 'P04', 'name': 'Gian'},
          {'id': 'P06', 'name': 'Kukuru'}, {'id': 'P07', 'name': 'Giga Zombie'}]


def scene():
    return dict(scene_id='S0112', event_id='E0112', grounded_plan_locked=True,
        evidence_sentence_plan_version=1,
        tts='Giga Zombie xuất hiện trên cao và đe dọa nhóm bạn.',
        observed_facts=[dict(fact_id='F1', text='Giga Zombie xuất hiện trên cao, đe dọa nhóm bạn',
                             shot_ids=['SHOT_000844'], canonical_actor_ids=['P07'])],
        locked_visual_shots=[dict(shot_id='SHOT_000844', start='01:24:18', end='01:24:24')])


def wrap(s):
    return {'parts': [{'scenes': [s]}]}


class IdentityContractTests(unittest.TestCase):
    def test_gian_kho_is_not_a_character_but_actual_gian_is(self):
        for text in ('Hành trình di cư gian khổ.', 'Thời gian trôi.', 'Gian nan vượt núi.'):
            self.assertFalse(name_in_text('Gian', text))
        self.assertTrue(name_in_text('Gian', 'Gian vượt núi.'))
        self.assertTrue(name_in_text('Gian', 'Kukuru gặp Gian tại bờ sông.'))

    def test_park_scene_rejects_doraemon_and_accepts_shizuka(self):
        event = dict(characters=['P01', 'P03', 'P04'], observed_facts=[dict(
            text='Shizuka và Gian chạy đến gọi Nobita.', canonical_actor_ids=['P01', 'P03', 'P04'])])
        s = dict(scene_id='S0018', tts='Doraemon và Gian chạy đến gọi Nobita.',
                 identity_contract=scene_identity_contract(event, PEOPLE))
        self.assertEqual(character_issues(s, PEOPLE)[0]['unexpected_names'], ['Doraemon'])
        s['tts'] = 'Shizuka và Gian chạy đến gọi Nobita.'
        self.assertEqual(character_issues(s, PEOPLE), [])

    def test_offscreen_mention_is_permitted_but_not_added_to_visible_people(self):
        event = dict(characters=['P01'], observed_facts=[dict(text='Nobita xem tờ giấy.',
            canonical_actor_ids=['P01'], spoken_text='Không biết Doraemon đang ở đâu.')])
        contract = scene_identity_contract(event, PEOPLE)
        self.assertNotIn('Doraemon', contract['visible_names'])
        self.assertIn('Doraemon', contract['mentioned_names'])
        self.assertEqual(character_issues(dict(tts='Nobita nhắc đến Doraemon.', identity_contract=contract), PEOPLE), [])
        self.assertTrue(character_issues(dict(tts='Giga Zombie tấn công Nobita.', identity_contract=contract), PEOPLE))

    def test_no_names_borrowed_from_neighbor_and_no_gian_from_adjective(self):
        event = dict(event_id='E0083', scene_id='S0083', start_seconds=0, end_seconds=6,
            characters=['P01', 'P06'], situation_narration=True,
            observed_facts=[dict(text='Kukuru kể về hành trình gian khổ.', canonical_actor_ids=['P06'])])
        plan = dict(boundaries=[0, 12], characters=PEOPLE, summaries=['Gian và Doraemon ở gần đó.'],
                    events_by_part=[[event]], story_beats_by_part=[[]])
        context = build_part_story_context(plan, 1)
        e = context['required_events'][0]
        self.assertNotIn('Gian', e['allowed_character_names'])
        self.assertNotIn('Doraemon', e['allowed_character_names'])
        self.assertEqual(character_issues(dict(e, tts='Kukuru kể hành trình gian khổ.'), PEOPLE), [])

    def test_clip_local_tokens_are_resolved_with_that_clips_mapping_only(self):
        raw = '[C1] gọi [CHAR=C2]. [SHOT_000001]'
        self.assertEqual(render_ids(raw, {'C1': 'Nobita', 'C2': 'Shizuka'}),
                         'Nobita gọi Shizuka. [SHOT_000001]')
        self.assertEqual(render_ids('[C1]', {'C1': 'Kukuru'}), 'Kukuru')

    def test_unproven_family_relation_is_not_used_as_description(self):
        c = profile(dict(id='P08', alias='bố của Kukuru', entity_kind='person'), strict=True)
        self.assertNotEqual(c['display_name'], 'bố của Kukuru')
        self.assertEqual(c['relationship_alias_candidate'], 'bố của Kukuru')

    def test_signature_invalidates_on_text_fact_identity_or_source_change(self):
        s = scene()
        original = audit_signature(s, 'film-a')
        for field, value in [('tts', 'Kukuru xuất hiện.'), ('observed_facts', []),
                             ('identity_contract', {'visible_names': ['Kukuru']})]:
            self.assertNotEqual(audit_signature(dict(s, **{field: value}), 'film-a'), original)
        self.assertNotEqual(audit_signature(s, 'film-b'), original)
        self.assertNotEqual(audit_signature(dict(s, scene_id='S0113'), 'film-a'), original)

    def test_conflicting_verifier_goes_to_local_video_and_logs_decision(self):
        s = scene()
        events, video_calls = [], []
        def text(cards):
            return {'checks': [dict(scene_id='S0112', faithful=False,
                reason='Hành động (đe dọa) không có trong facts.') ]}
        def video(cards):
            video_calls.append(cards)
            return {'checks': [dict(scene_id='S0112', faithful=True, reason='')]}
        checked = audit_planned_payload(wrap(s), text, video,
            diagnostic=lambda event, data: events.append((event, data)))
        self.assertTrue(checked['parts'][0]['scenes'][0]['grounding_audit_passed'])
        self.assertEqual([c['scene_id'] for c in video_calls[0]], ['S0112'])
        decisions = [d for e, d in events if e == 'AUDIT_SCENE_DECISION']
        self.assertEqual(decisions[0]['diagnostic_category'], 'VERIFIER_FACT_CONFLICT')
        self.assertEqual(decisions[0]['backend_decision'], 'reject')
        self.assertEqual(decisions[1]['backend_decision'], 'pass')
        self.assertTrue(any(e == 'AUDIT_EVIDENCE_SENT' for e, _ in events))
        self.assertTrue(any(e == 'AUDIT_VERIFIER_RESPONSE' for e, _ in events))

    def test_conflict_never_auto_passes_when_video_verdict_missing(self):
        checked = audit_planned_payload(wrap(scene()), lambda _: {'checks': [dict(
            scene_id='S0112', faithful=False, reason='(đe dọa) không có trong facts.')]},
            lambda _: {'checks': []})
        s = checked['parts'][0]['scenes'][0]
        self.assertFalse(s['grounding_audit_passed'])
        self.assertTrue(s['grounding_audit_pending'])

    def test_old_pass_not_reused_for_new_identity_and_requested_repair_not_rolled_back(self):
        cache = {}
        def verifier(cards):
            return {'checks': [dict(scene_id=c['scene_id'], faithful=True, reason='') for c in cards]}
        previous = audit_narrations(wrap(scene()), verifier, save=lambda x: cache.update(x))
        modified = copy.deepcopy(previous)
        modified['parts'][0]['scenes'][0]['identity_contract'] = {'visible_names': ['Kukuru']}
        checked = audit_narrations(modified, Mock(side_effect=AssertionError('cache only')),
                                    checkpoint=cache, max_attempts=0)
        self.assertTrue(checked['parts'][0]['scenes'][0]['grounding_audit_pending'])
        kept = preserve_verified_scenes(previous, checked, requested_scene_ids=['S0112'])
        self.assertEqual(kept, checked)
        self.assertEqual(preserve_verified_scenes(previous, checked), previous)


if __name__ == '__main__':
    unittest.main()
