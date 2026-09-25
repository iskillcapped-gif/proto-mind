import json
import threading
import time
import unittest
from unittest.mock import patch

from proto_mind.native_claude_metadata import ClaudeMetadataReader, normalize_models, normalize_usage
from proto_mind.tests import test_native_claude


class ClaudeMetadataTests(unittest.TestCase):
    setUp = test_native_claude.ClaudeTests.setUp

    def reader(self):
        runtime_patch = patch('proto_mind.native_claude_metadata.runtime_path', return_value=self.runtime)
        runtime_patch.start(); self.addCleanup(runtime_patch.stop)
        reader = ClaudeMetadataReader(self.state)
        self.addCleanup(reader.close)
        return reader

    def test_reads_real_worker_catalog_and_percentages_without_model_query(self):
        reader = self.reader()
        value = reader.read()
        self.assertEqual(value['models'][1]['id'], 'claude-opus-5-5')
        self.assertEqual(value['models'][2]['title'], 'Haiku 4.5')
        self.assertEqual([w['remaining_percent'] for w in value['windows']], [100,97])
        self.assertNotIn('SECRET', json.dumps(value))
        self.assertFalse((self.state / 'claude-profile/sdk-observed.json').exists())
        self.assertTrue(value['limits_updated_at'])

    def test_unavailable_usage_preserves_catalog_without_fabricating_percentages(self):
        (self.state / 'claude-profile/metadata-mode').write_text('unsupported')
        value = self.reader().read()
        self.assertTrue(value['models'])
        self.assertEqual(value['windows'], [])
        self.assertEqual(value['limits_error'], 'usage_unavailable')
        self.assertIsNone(value['limits_updated_at'])
        self.assertNotIn('SECRET', json.dumps(value))

    def test_account_switch_during_read_discards_previous_account_measurements(self):
        reader = self.reader()
        accounts = [{'installed':True,'connected':True,'email':name} for name in ['a@example.invalid','b@example.invalid']]
        with patch('proto_mind.native_claude_metadata.status', side_effect=accounts): value = reader.read()
        self.assertFalse(value['connected'])
        self.assertEqual(value['windows'], [])
        self.assertEqual(value['models'], [])
        self.assertEqual(value['email'], '')
        self.assertEqual(value['limits_error'], 'account_changed')

    def test_disconnected_metadata_does_not_initialize_profile(self):
        reader = self.reader()
        with patch('proto_mind.native_claude_metadata.status', return_value={'installed':True,'connected':False}):
            value = reader.read()
        self.assertIsNone(reader.transport.process)
        self.assertEqual(value['models'], [])
        self.assertEqual(value['windows'], [])

    def test_close_releases_only_owned_metadata_worker(self):
        (self.state / 'claude-profile/metadata-mode').write_text('hang')
        reader = self.reader()
        values = []
        thread = threading.Thread(target=lambda: values.append(reader.read())); thread.start()
        deadline = time.monotonic() + 5
        while reader.transport.process is None and time.monotonic() < deadline: time.sleep(.01)
        self.assertIsNotNone(reader.transport.process)
        reader.close(); thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(values[0]['windows'], [])
        with self.assertRaises(RuntimeError): reader.read()

    def test_exact_catalog_ids_context_suffix_and_available_efforts(self):
        rows = normalize_models([
            {'value':'opus','resolvedModel':'claude-opus-5-5','supportsEffort':True,'supportedEffortLevels':['low','nonsense',True]},
            {'value':'claude-fable-5-1[1m]','resolvedModel':'claude-fable-5-1','displayName':'Fable'},
            {'value':'haiku','resolvedModel':'claude-haiku-4-5-20251001'},
            {'value':'sonnet','displayName':'Sonnet'},
            {'value':'bad\nvalue','resolvedModel':'claude-opus-5-5'},
            {'value':'duplicate','resolvedModel':'claude-opus-5-5'}])
        self.assertEqual([r['id'] for r in rows], ['claude-opus-5-5','claude-fable-5-1[1m]','claude-haiku-4-5-20251001'])
        self.assertEqual(rows[0]['efforts'], ['low'])
        self.assertEqual(rows[1]['title'], 'Fable 5.1')
        self.assertEqual(rows[2]['efforts'], [])

    def test_usage_units_absence_and_model_scopes(self):
        rates = {'five_hour':{'utilization':.3}, 'seven_day':{'utilization':None},
                 'unknown':{'utilization':0}, 'limits':[{'kind':'weekly_scoped','percent':62,
                    'scope':{'model':{'display_name':'Fable'}},'resets_at':'2030-09-30T00:00:00Z'}]}
        result = normalize_usage({'rate_limits_available':True,'rate_limits':rates})
        self.assertIsNone(result['windows'][0]['remaining_percent'])
        self.assertEqual(result['windows'][1]['remaining_percent'], 99.7)
        self.assertEqual(result['windows'][2]['remaining_percent'], 38)
        self.assertEqual(result['windows'][2]['title'], 'Fable')
        self.assertEqual(normalize_usage({'rate_limits_available':False,'rate_limits':rates})['windows'], [])
        for invalid in [True, '4', float('nan'), float('inf'), -1]:
            value = normalize_usage({'rate_limits_available':True,'rate_limits':{'five_hour':{'utilization':invalid}}})
            self.assertIsNone(value['windows'][0]['remaining_percent'])


if __name__ == '__main__': unittest.main()
