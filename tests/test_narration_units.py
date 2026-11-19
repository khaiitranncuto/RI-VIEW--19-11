import copy
import json
import unittest

from narration_units import (generate_unit_chunks, plan_narration_units, unit_prompt,
    unit_response, validate_narration_unit_order)
from evidence_writer import build_sentence_plan, bind_planned_scenes, write_batch
from flat_writer import flat_prompt, flat_schema, flat_to_paragraphs
from narrative_contract import verify_script, sentences
from recap_pipeline import coerce_single_part_response, merge_single_part_responses, clamp_payload_narrations
from sentence_visual_contract import enforce_sentence_visual_contract, preflight_visual_plan
from source_grounded_writer import is_source_grounded


class NarrationUnitTests(unittest.TestCase):
    def test_structural_repair_preserves_good_units_and_exact_quota(self):
        event = dict(event_id='E1', sentence_quota=3, sentence_slots=[
            dict(unit_id='U1'), dict(unit_id='U2'), dict(unit_id='U3')])
        previous = {'scenes': [dict(event_id='E1', narration_units=[
            dict(unit_id='U1', text='First valid sentence.'),
            dict(unit_id='U2', text='Two sentences. Invalid unit.'),
            dict(unit_id='U3', text='Last valid sentence.')])]}
        requested = []
        def generate(events, prompt):
            requested.extend(s['unit_id'] for s in events[0]['sentence_slots'])
            return json.dumps({'sentences': [dict(event_id='E1', unit_id='U2',
                text='Repaired sentence.')]})
        raw = generate_unit_chunks(event, {}, generate, lambda *args: 'prompt',
            previous, 'NARRATION_UNIT_ONE_SENTENCE_REQUIRED:E1')
        rows = json.loads(raw)['sentences']
        self.assertEqual(requested, ['U2'])
        self.assertEqual([r['unit_id'] for r in rows], ['U1', 'U2', 'U3'])
        self.assertTrue(all(len(sentences(r['text'])) == 1 for r in rows))
        self.assertEqual(rows[0]['text'], 'First valid sentence.')
        self.assertEqual(rows[2]['text'], 'Last valid sentence.')

    def plan(self):
        e = dict(event_id='E0001', scene_id='S0001', sentence_quota=1,
            start_seconds=0, end_seconds=12, grounded_plan_locked=True,
            observed_facts=[dict(fact_id='F1', text='Kukuru nhảy ra khỏi tủ.', shot_ids=['SHOT_000001']),
                dict(fact_id='F2', text='Cậu lao về phía nhóm bạn.', shot_ids=['SHOT_000002'])],
            visual_sources=[dict(shot_id='SHOT_000001', fact_ids=['F1'], start_seconds=0, end_seconds=6),
                dict(shot_id='SHOT_000002', fact_ids=['F2'], start_seconds=6, end_seconds=12)])
        return plan_narration_units(build_sentence_plan(dict(events_by_part=[[e]],
            sentence_contract={'target_count': 1}, scene_contract={})))

    def response(self):
        return {'sentences': [dict(event_id='E0001', unit_id='E0001_U001',
            text='Kukuru nhảy ra khỏi tủ, khiến cả nhóm hoảng hốt, rồi cậu lập tức lao nhanh về phía những người bạn.')]}

    def test_one_sentence_can_have_two_clauses_and_two_shots(self):
        plan = self.plan()
        self.assertTrue(preflight_visual_plan(plan, 12)['passed'])
        e = plan['events_by_part'][0][0]
        self.assertEqual(e['sentence_slots'][0]['fact_ids'], ['F1', 'F2'])
        scene = bind_planned_scenes(unit_response(self.response(), [e]), [e])[0]
        self.assertEqual(len(sentences(scene['tts'])), 1)
        self.assertEqual(len(scene['sentence_proofs']), 1)
        self.assertEqual(len(scene['locked_visual_shots']), 2)
        self.assertTrue(is_source_grounded(scene))

    def test_writer_prompt_keeps_full_metadata_while_compacting_instructions(self):
        event = self.plan()['events_by_part'][0][0]
        event['sentence_slots'][0]['transition_contract'] = {
            'version': 1, 'relation': 'location_change', 'requires_bridge': True,
            'previous_event_id': 'E0000', 'current_event_id': 'E0001',
            'previous_anchor': 'Cáº£nh trÆ°á»›c.', 'current_anchor': 'Cáº£nh hiá»‡n táº¡i.',
            'previous_location': 'NhÃ ', 'current_location': 'Rá»«ng',
            'semantic_goal': 'introduce_the_confirmed_new_location',
            'forbidden_inferences': ['unverified_causality'],
            'evidence_basis': ['planner_temporal_relation'],
            'variation_key': 'location_change:E0001',
            'wording_policy': 'free_semantic_paraphrase',
        }
        prompt = unit_prompt([event], {})
        self.assertIn('location_change', prompt)
        self.assertIn('introduce_the_confirmed_new_location', prompt)
        self.assertIn('unverified_causality', prompt)
        self.assertIn('source_start', prompt)
        self.assertIn('previous_event_id', prompt)
        self.assertIn('evidence_basis', prompt)
        self.assertIn('variation_key', prompt)

    def test_single_unit_prompt_can_exceed_batching_soft_limit(self):
        event = self.plan()['events_by_part'][0][0]
        prompts = []
        def oversized_prompt(*_):
            return 'x' * 16000
        def generate(events, prompt):
            prompts.append(prompt)
            return json.dumps(self.response())
        result = json.loads(generate_unit_chunks(
            event, {}, generate, oversized_prompt))
        self.assertEqual(result, self.response())
        self.assertEqual([len(prompt) for prompt in prompts], [16000])

    def test_unit_ids_survive_normalization_merge_and_export(self):
        e = self.plan()['events_by_part'][0][0]
        scene = bind_planned_scenes(unit_response(self.response(), [e]), [e])[0]
        normalized = coerce_single_part_response(json.dumps({'scenes': [scene]}), 1, 12, 40,
            locked_event_by_id={'E0001': e})
        payload = merge_single_part_responses([normalized], [0, 12], 40, single_timeline=True)
        payload = clamp_payload_narrations(payload)
        s = payload['parts'][0]['scenes'][0]
        self.assertTrue(is_source_grounded(s))
        s.update(grounding_audit_passed=True, grounding_audit_pending=False)
        report = enforce_sentence_visual_contract(payload, 1, 12)
        self.assertTrue(report['passed'])
        self.assertEqual(verify_script(s['tts'], 1, 40, unit_count=report['actual'])[0], 1)
        self.assertEqual(verify_script(s['tts'], 1, 40, unit_texts=[s['tts']])[0], 1)
        with self.assertRaisesRegex(ValueError, 'UNIT_TEXT_MISMATCH'):
            verify_script('Kukuru nhảy ra.', 1, 40, unit_texts=[s['tts']])

    def test_missing_duplicate_and_unknown_unit_ids_are_rejected(self):
        e = self.plan()['events_by_part'][0][0]
        for rows in [[], [dict(event_id='E0001', unit_id='BAD', text='Có hình.')], self.response()['sentences'] * 2]:
            mapped = unit_response({'sentences': rows}, [e])
            self.assertIn('IDS_INVALID', mapped['scenes'][0]['format_error'])

    def test_two_grammatical_sentences_in_one_unit_are_rejected(self):
        e = self.plan()['events_by_part'][0][0]
        payload = self.response()
        payload['sentences'][0]['text'] = (
            'Kukuru nhảy ra khỏi tủ. Cậu lao về phía nhóm bạn.'
        )
        mapped = unit_response(payload, [e])
        self.assertIn('ONE_SENTENCE_REQUIRED', mapped['scenes'][0]['format_error'])

    def test_materially_short_unit_is_kept_with_soft_word_warning(self):
        e = self.plan()['events_by_part'][0][0]
        payload = self.response()
        payload['sentences'][0]['text'] = 'Kukuru nhảy ra ngoài.'
        mapped = unit_response(payload, [e])
        scene = mapped['scenes'][0]
        self.assertNotIn('format_error', scene)
        self.assertGreater(scene['word_budget_warning']['distance'], 0)

    def test_dispatch_and_cache_use_units_without_punctuation_count(self):
        e = self.plan()['events_by_part'][0][0]
        self.assertIn('unit_id', flat_schema([e])['properties']['sentences']['items']['required'])
        prompt = flat_prompt([e], {})
        self.assertIn('MOI ID BAT BUOC DUNG MOT CAU NGU PHAP', prompt)
        saved, raw = [], []
        rows = write_batch([e], {}, lambda *_: json.dumps(self.response()),
            prompt_builder=flat_prompt, response_adapter=flat_to_paragraphs,
            save=lambda d: saved.extend(d), save_raw=lambda text, _: raw.append(text))
        again = write_batch([e], {}, lambda *_: self.fail('cache must be reused'), candidates=saved,
            prompt_builder=flat_prompt, response_adapter=flat_to_paragraphs)
        self.assertEqual(rows, again)
        self.assertEqual(json.loads(raw[0]), self.response())

    def test_english_cached_draft_is_repaired_in_vietnamese(self):
        event = self.plan()['events_by_part'][0][0]
        english = self.response()
        english['sentences'][0]['text'] = (
            'The frightened boy suddenly jumps out of the cabinet and quickly runs toward all of his surprised friends across the room.')
        bad_cache = unit_response(english, [event])
        prompts = []
        def generate(events, prompt):
            prompts.append(prompt)
            return json.dumps(self.response())
        rows = write_batch([event], {}, generate, candidates=[bad_cache],
            prompt_builder=flat_prompt, response_adapter=flat_to_paragraphs)
        self.assertEqual(len(prompts), 1)
        self.assertIn('NGÔN NGỮ BẮT BUỘC', prompts[0])
        self.assertIn('RECAP_LANGUAGE_INVALID', prompts[0])
        self.assertEqual(rows[0]['tts'], self.response()['sentences'][0]['text'])

    def test_persistently_english_output_is_not_accepted(self):
        event = self.plan()['events_by_part'][0][0]
        english = self.response()
        english['sentences'][0]['text'] = (
            'The frightened boy suddenly jumps out of the cabinet and quickly runs toward all of his surprised friends across the room.')
        calls = []
        def generate(events, prompt):
            calls.append(prompt)
            return json.dumps(english)
        with self.assertRaisesRegex(ValueError, 'RECAP_LANGUAGE_INVALID'):
            write_batch([event], {}, generate, prompt_builder=flat_prompt,
                        response_adapter=flat_to_paragraphs)
        self.assertEqual(len(calls), 2)

    def test_bad_raw_response_is_retained_before_adapter_rejects_it(self):
        e = self.plan()['events_by_part'][0][0]
        raw = []
        with self.assertRaises(ValueError):
            write_batch([e], {}, lambda *_: 'broken JSON', prompt_builder=flat_prompt,
                response_adapter=flat_to_paragraphs, save_raw=lambda text, _: raw.append(text))
        self.assertEqual(raw, ['broken JSON', 'broken JSON'])

    def test_absent_assigned_visual_blocks_export(self):
        e = self.plan()['events_by_part'][0][0]
        scene = bind_planned_scenes(unit_response(self.response(), [e]), [e])[0]
        scene.update(sentence_quota=1, grounded_plan_locked=True, grounding_audit_passed=True)
        scene['locked_visual_shots'].pop()
        with self.assertRaises(ValueError):
            enforce_sentence_visual_contract({'parts': [{'scenes': [scene]}]}, 1, 12)

    def test_distinct_facts_are_locked_in_shot_time_order(self):
        e = dict(event_id='E0003', scene_id='S0003', sentence_quota=4,
            grounded_plan_locked=True,
            observed_facts=[
                dict(fact_id='F_LATE', text='Diễn biến muộn.', shot_ids=['SHOT_000036']),
                dict(fact_id='F_EARLY', text='Diễn biến sớm.', shot_ids=['SHOT_000030']),
                dict(fact_id='F_MID1', text='Diễn biến giữa một.', shot_ids=['SHOT_000032']),
                dict(fact_id='F_MID2', text='Diễn biến giữa hai.', shot_ids=['SHOT_000035'])],
            visual_sources=[
                dict(shot_id='SHOT_000036', start_seconds=210, end_seconds=216),
                dict(shot_id='SHOT_000030', start_seconds=174, end_seconds=186),
                dict(shot_id='SHOT_000035', start_seconds=204, end_seconds=210),
                dict(shot_id='SHOT_000032', start_seconds=186, end_seconds=192)])
        plan = dict(events_by_part=[[e]], sentence_contract={'target_count': 4},
                    scene_contract={}, evidence_capacity_policy='distinct_facts')
        locked = plan_narration_units(build_sentence_plan(plan))['events_by_part'][0][0]
        self.assertEqual([u['fact_ids'][0] for u in locked['sentence_slots']],
                         ['F_EARLY', 'F_MID1', 'F_MID2', 'F_LATE'])
        self.assertEqual([u['source_start'] for u in locked['sentence_slots']],
                         [174, 186, 204, 210])
        self.assertTrue(validate_narration_unit_order(locked))

    def test_long_fact_does_not_take_a_late_shot_past_the_next_fact(self):
        e = dict(event_id='E0030', scene_id='S0030', sentence_quota=2,
            grounded_plan_locked=True,
            observed_facts=[
                dict(fact_id='F_WIDE', text='Một diễn biến kéo dài.',
                     shot_ids=['SHOT_000017', 'SHOT_000025']),
                dict(fact_id='F_MIDDLE', text='Một hành động xảy ra ở giữa.',
                     shot_ids=['SHOT_000021'])],
            visual_sources=[
                dict(shot_id='SHOT_000017', start_seconds=100, end_seconds=110),
                dict(shot_id='SHOT_000021', start_seconds=120, end_seconds=130),
                dict(shot_id='SHOT_000025', start_seconds=150, end_seconds=160)])
        plan = dict(events_by_part=[[e]], sentence_contract={'target_count': 2},
                    scene_contract={}, evidence_capacity_policy='distinct_facts')
        locked = plan_narration_units(build_sentence_plan(plan))['events_by_part'][0][0]
        first, second = locked['sentence_slots']
        self.assertEqual(first['shot_ids'], ['SHOT_000017'])
        self.assertEqual(second['shot_ids'], ['SHOT_000021'])
        self.assertLessEqual(first['source_end'], second['source_start'])

    def test_explicit_fact_ownership_beats_overlapping_merged_shot_ids(self):
        e = dict(event_id='E0004', scene_id='S0004', sentence_quota=2,
            grounded_plan_locked=True,
            observed_facts=[
                dict(fact_id='F1', text='Nobita tuyên bố rời nhà.',
                     shot_ids=['SHOT_000038', 'SHOT_000039']),
                dict(fact_id='F2', text='Doraemon tiếp tục đọc truyện.',
                     shot_ids=['SHOT_000039', 'SHOT_000040'])],
            visual_sources=[
                dict(shot_id='SHOT_000038', shot_ids=['SHOT_000038', 'SHOT_000039'],
                     fact_ids=['F1'], start_seconds=222, end_seconds=234),
                dict(shot_id='SHOT_000040', shot_ids=['SHOT_000040'],
                     fact_ids=['F2'], start_seconds=234, end_seconds=240)])
        plan = dict(events_by_part=[[e]], sentence_contract={'target_count': 2},
                    scene_contract={}, evidence_capacity_policy='distinct_facts')
        locked = plan_narration_units(build_sentence_plan(plan))['events_by_part'][0][0]
        first, second = locked['sentence_slots']
        self.assertEqual(first['fact_ids'], ['F1'])
        self.assertEqual(first['visual_ids'], ['V001'])
        self.assertEqual(second['fact_ids'], ['F2'])
        self.assertEqual(second['visual_ids'], ['V002'])
        self.assertLessEqual(first['source_end'], second['source_start'])
        self.assertTrue(validate_narration_unit_order(locked))

    def test_fractional_backend_time_is_not_lost_to_display_timecode_rounding(self):
        start = 1438.7815384615385
        e = dict(event_id='E0018', scene_id='S0018', sentence_quota=2,
            grounded_plan_locked=True,
            observed_facts=[
                dict(fact_id='F004_0001_01', text='Doraemon dùng bảo bối tạo mưa.',
                     shot_ids=['SHOT_000240']),
                dict(fact_id='F004_0001_02', text='Cây con lớn lên nhờ mưa.',
                     shot_ids=['SHOT_000241'])],
            visual_sources=[
                dict(shot_id='SHOT_000240', fact_ids=['F004_0001_01'],
                     start_seconds=start, end_seconds=1440.0,
                     start='00:23:58.78', end='00:24:00.00'),
                dict(shot_id='SHOT_000241', fact_ids=['F004_0001_02'],
                     start_seconds=1440.0, end_seconds=1446.0,
                     start='00:24:00.00', end='00:24:06.00')])
        plan = dict(events_by_part=[[e]], sentence_contract={'target_count': 2},
                    scene_contract={}, evidence_capacity_policy='distinct_facts')
        locked = plan_narration_units(build_sentence_plan(plan))['events_by_part'][0][0]
        self.assertEqual(locked['sentence_slots'][0]['visual_ids'], ['V001'])
        self.assertEqual(locked['sentence_slots'][0]['source_start'], start)
        self.assertEqual(locked['sentence_slots'][1]['visual_ids'], ['V002'])
