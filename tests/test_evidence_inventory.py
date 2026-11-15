import unittest

from evidence_inventory import detail_windows, inventory
from narrative_contract import allocate_sentences


class EvidenceInventoryTests(unittest.TestCase):
    def test_review_can_cover_all_sparse_intervals_and_resume_without_duplicates(self):
        chunks = [{'events': [{'start_seconds': 120, 'end_seconds': 420,
                   'grounded_facts': [{'fact_id': 'F1', 'shot_ids': ['SHOT_1']}]}]}]
        windows = detail_windows(chunks, 600, 281)
        self.assertEqual(len(windows), 10)
        self.assertTrue(all(w['end_seconds'] - w['start_seconds'] <= 60 for w in windows))
        self.assertEqual(windows[0]['reason'], 'missing_story_observations')
        reviewed = [[w['start_seconds'], w['end_seconds']] for w in windows[:4]]
        remaining = detail_windows(chunks, 600, 281, reviewed=reviewed)
        self.assertEqual(len(remaining), 6)
        self.assertFalse({tuple(row) for row in reviewed} & {
            (w['start_seconds'], w['end_seconds']) for w in remaining})
        self.assertEqual(inventory(chunks)['source_shots'], 1)
        self.assertEqual(detail_windows(chunks, 600, 1), [])

    def test_fact_policy_does_not_silently_lower_duration_contract(self):
        plan = {'events_by_part': [[{'observed_facts': [{'text': 'A'}]}]],
                'scene_contract': {}, 'evidence_capacity_policy': 'distinct_facts'}
        with self.assertRaisesRegex(ValueError, 'SENTENCE_EVIDENCE_SHORTAGE'):
            allocate_sentences(plan, 8, 160)
        self.assertNotIn('sentence_quota', plan['events_by_part'][0][0])


if __name__ == '__main__':
    unittest.main()
