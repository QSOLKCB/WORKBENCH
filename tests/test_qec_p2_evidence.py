"""Offline verification of retained real-P2 evidence, including resealed errors."""
from copy import deepcopy
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from qec_acceptance import digest, read_json, seal, write_json
from qec_p2_acceptance import verify_evidence

EVIDENCE = ROOT / 'evidence/p2-qec'


class P2EvidenceTests(unittest.TestCase):
    def test_retained_three_operation_real_gate(self):
        comparison = verify_evidence(EVIDENCE)
        self.assertEqual(comparison['ququart']['artifact_count_per_mode'], 15)
        self.assertEqual(comparison['qutrit']['artifact_count_per_mode'], 13)
        self.assertTrue(all(result['byte_identical'] for result in comparison.values()))

    def test_resealed_identity_receipt_and_browser_errors_are_rejected(self):
        changes = [
            ('qec-source.json', lambda value: value.update(commit='0' * 40)),
            ('environment.json', lambda value: value['packages']['scipy'].update(version='0.0')),
            ('descriptor.json', lambda value: value.update(protocol='qec-capabilities/99')),
            ('validation/cli.json', lambda value: value.update(passed=False)),
            ('browser.json', lambda value: value.update(engine='Node DOM fixture')),
            ('browser.json', lambda value: value['runs'][0]['view'].update(hidden=True)),
            ('browser.json', lambda value: value['runs'][0]['view'].update(text='Artifact manifest (backend-reported)')),
            ('summary.json', lambda value: value.update(comparison={})),
            ('commands/contract-tests.json', lambda value: value.update(exit_code=1)),
            ('commands/direct-qutrit-benchmark.json', lambda value: value.update(exit_code=1)),
        ]
        for name, mutate in changes:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / 'evidence'
                shutil.copytree(EVIDENCE, target)
                value = deepcopy(read_json(target / name)); mutate(value)
                write_json(target / name, value); seal(target)
                with self.assertRaises(ValueError):
                    verify_evidence(target)

    def test_rehashed_run_cannot_claim_a_different_invocation(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'evidence'
            shutil.copytree(EVIDENCE, target)
            path = target / 'runs/cli-qutrit-benchmark.json'
            record = read_json(path)
            record['execution']['argv'][-1] = '--stress-limit=9'
            record.pop('record_sha256'); record['record_sha256'] = digest(record)
            write_json(path, record)
            write_json(target / 'store' / (record['id'] + '.json'), record)
            command = read_json(target / 'commands/cli-qutrit-benchmark.json')
            write_json(target / command['stdout'], record)
            seal(target)
            with self.assertRaisesRegex(ValueError, 'argv/cwd'):
                verify_evidence(target)

    def test_resealed_direct_invocations_must_match_every_locked_operation(self):
        changes = [lambda command: command['argv'].__setitem__(0, '/foreign/python'),
                   lambda command: command['argv'].__setitem__(2, 'foreign.module'),
                   lambda command: command['argv'].__setitem__(-1, '--foreign=1'),
                   lambda command: command.update(cwd='/foreign/cwd'),
                   lambda command: command.update(stdout='validation/direct.json')]
        for label in ('ququart-benchmark', 'ququart-validate', 'qutrit-benchmark'):
            for mutate in changes:
                with self.subTest(operation=label, mutation=mutate), tempfile.TemporaryDirectory() as directory:
                    target = Path(directory) / 'evidence'; shutil.copytree(EVIDENCE, target)
                    path = target / f'commands/direct-{label}.json'
                    command = read_json(path); mutate(command); write_json(path, command); seal(target)
                    with self.assertRaisesRegex(ValueError, 'Direct command argv/cwd'):
                        verify_evidence(target)

    def test_resealed_source_map_cannot_change_omit_or_add_python_files(self):
        changes = [lambda files: files.update({'__init__.py': '0' * 64}),
                   lambda files: files.pop('__init__.py'),
                   lambda files: files.update({'foreign.py': '0' * 64})]
        for mutate in changes:
            with self.subTest(mutation=mutate), tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / 'evidence'; shutil.copytree(EVIDENCE, target)
                path = target / 'qec-source.json'
                source = read_json(path); mutate(source['python_files']); write_json(path, source); seal(target)
                with self.assertRaisesRegex(ValueError, 'pinned source map'):
                    verify_evidence(target)

    def test_resealed_json_format_changes_do_not_claim_byte_parity(self):
        for name in ('artifacts/cli/qutrit/benchmark_manifest.json', 'validation/cli.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / 'evidence'
                shutil.copytree(EVIDENCE, target)
                with (target / name).open('a') as handle:
                    handle.write('\n')
                seal(target)
                with self.assertRaisesRegex(ValueError, 'bytes differ|receipts differ'):
                    verify_evidence(target)

    def test_artifact_and_unlisted_file_mutations_are_rejected(self):
        for name in ('artifacts/browser/qutrit/deterministic_stress_corpus.csv', 'unlisted.txt'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / 'evidence'
                shutil.copytree(EVIDENCE, target)
                with (target / name).open('a') as handle:
                    handle.write('changed\n')
                with self.assertRaisesRegex(ValueError, 'checksum|Incomplete'):
                    verify_evidence(target)


if __name__ == '__main__':
    unittest.main()
