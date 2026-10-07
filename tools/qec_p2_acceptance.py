#!/usr/bin/env python3
"""Pinned installed-QEC descriptor gate; optional acceptance tools only."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from qec_acceptance import (ROOT, MODES, checked_checksum, digest, json_loads,
                            qec_digest, read_json, seal, sha256, verify_artifacts,
                            verify_environment, verify_validation, write_json)
from qsol_workbench.runtime import Runtime
from qsol_workbench.web import make_server

LOCK = ROOT / 'examples/qec-p2-lock.json'
ACTIONS = ('qec.ququart.benchmark', 'qec.ququart.validate', 'qec.qutrit.benchmark')
MODULES = ('qec.benchmark.ququart_battery.cli', 'qec.benchmark.ququart_battery.validate_cli',
           'qec.benchmark.qutrit_battery.cli')


def report(directory, action, lock):
    if action == ACTIONS[0]:
        return verify_artifacts(directory, lock)
    directory = Path(directory)
    manifest = read_json(directory / 'benchmark_manifest.json')
    checked_checksum(manifest, 'sha256', qec_digest)
    if (manifest.get('schema') != 'qec.qutrit-decoder-benchmark.v1' or
            manifest.get('deterministic') is not True or set(manifest.get('files', {})) != set(lock['qutrit_artifacts'])):
        raise ValueError('Unexpected qutrit artifact contract')
    if {p.name for p in directory.iterdir()} != set(manifest['files']) | {'benchmark_manifest.json'}:
        raise ValueError('Missing or unexpected qutrit artifacts')
    for name, expected in manifest['files'].items():
        path = directory / name
        if Path(name).name != name or path.is_symlink() or not path.is_file() or sha256(path) != expected:
            raise ValueError('Qutrit artifact checksum mismatch: ' + name)
    methodology = read_json(directory / 'methodology.json')
    checked_checksum(methodology, 'sha256', qec_digest)
    if (methodology['stress_corpus']['limit_per_weight'] != lock['stress_limit'] or
            methodology['sha256'] != manifest['methodology_sha256'] or
            sha256(directory / 'historical_v3_baseline.csv') != lock['baseline_sha256'] or
            manifest['historical_v3_sha256'] != lock['baseline_sha256']):
        raise ValueError('Qutrit methodology or historical baseline differs from requested inputs')
    return manifest


def parameters(output, root, mode, action, lock):
    if action == ACTIONS[0]:
        return {**lock['parameters'], 'output': str(output / 'artifacts' / mode / 'ququart')}
    if action == ACTIONS[1]:
        source = output / 'artifacts/direct/ququart'
        return {'claims': str(source / 'report_claims.json'), 'evidence': str(source),
                'output': str(output / 'validation' / (mode + '.json'))}
    return {'output': str(output / 'artifacts' / mode / 'qutrit'),
            'v3_baseline': str(root / 'qec_data_prepared.csv'), 'stress_limit': lock['stress_limit']}


def direct_argv(python, action, params):
    return [python, '-m', MODULES[ACTIONS.index(action)]] + [
        '--' + name.replace('_', '-') + '=' + str(value) for name, value in params.items()]


def verify_source_map(hashes, lock):
    if (not isinstance(hashes, dict) or len(hashes) != lock['python_file_count'] or
            digest(hashes) != lock['python_files_sha256']):
        raise ValueError('QEC Python source inventory differs from pinned source map')


def verify_record(record, action, params, environment, source):
    checked_checksum(record, 'record_sha256', digest)
    if (record.get('protocol') != 'qsol-workbench-run/1' or record.get('action') != action or record.get('parameters') != params or
            record.get('status') != 'succeeded' or record.get('persistence_error') or
            record.get('exit_code') != 0 or record.get('transport_status') != 'succeeded'):
        raise ValueError('WORKBENCH run action, parameters or outcome mismatch')
    capability = record['capability']
    checked_checksum(capability, 'schema_sha256', digest)
    backend = capability['backend']
    if (backend.get('discovery') != 'descriptor' or backend.get('descriptor_protocol') != 'qec-capabilities/1' or
            backend.get('python') != environment['executable'] or backend.get('version') != '173.0.0' or
            record['execution']['argv'][0] != environment['executable']):
        raise ValueError('WORKBENCH backend identity mismatch')
    expected_argv = [environment['executable'], '-m', MODULES[ACTIONS.index(action)]]
    expected_argv += [field['flag'] + '=' + str(params[field['name']]) for field in capability['fields'] if field['name'] in params]
    if record['execution']['argv'] != expected_argv or record['execution']['cwd'] != backend['cwd']:
        raise ValueError('WORKBENCH argv/cwd differs from declared parameters')
    module = MODULES[ACTIONS.index(action)]
    if (record['execution']['argv'][1:3] != ['-m', module] or
            backend['module_sha256'] != source['python_files'][module[4:].replace('.', '/') + '.py']):
        raise ValueError('WORKBENCH command identity mismatch')
    for name, identity in backend['implementation_modules'].items():
        if identity['module_sha256'] != source['python_files'][name[4:].replace('.', '/') + '.py']:
            raise ValueError('Descriptor implementation identity mismatch')


def verify_evidence(directory):
    directory = Path(directory).resolve()
    entries = {}
    for line in (directory / 'SHA256SUMS').read_text().splitlines():
        expected, name = line.split('  ', 1)
        path = directory / name
        if name in entries or path.is_symlink() or not path.resolve().is_relative_to(directory):
            raise ValueError('Unsafe evidence inventory')
        if not path.is_file() or sha256(path) != expected:
            raise ValueError('Evidence checksum mismatch: ' + name)
        entries[name] = expected
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob('*')
              if p.is_file() and p != directory / 'SHA256SUMS'}
    if set(entries) != actual:
        raise ValueError('Incomplete evidence inventory')
    lock, summary = read_json(directory / 'lock.json'), read_json(directory / 'summary.json')
    if (lock != read_json(LOCK) or summary.get('status') != 'passed' or
            summary.get('modes') != list(MODES) or summary.get('qec_commit') != lock['commit']):
        raise ValueError('Incomplete or incorrectly pinned P2 gate')
    environment, source = read_json(directory / 'environment.json'), read_json(directory / 'qec-source.json')
    verify_environment(environment, lock)
    if (source.get('commit') != lock['commit'] or source.get('installed_matches_source') is not True or
            environment['packages']['qec']['version'] != lock['package_version'] or
            environment['prefix'] == environment['base_prefix']):
        raise ValueError('QEC source/environment identity mismatch')
    verify_source_map(source.get('python_files'), lock)
    descriptor = read_json(directory / 'descriptor.json')
    if descriptor.get('protocol') != 'qec-capabilities/1' or [a['id'] for a in descriptor['actions']] != list(ACTIONS):
        raise ValueError('Missing backend-owned descriptors')
    discovery = read_json(directory / 'discovery.json')
    if [a['id'] for a in discovery['actions']] != list(ACTIONS):
        raise ValueError('WORKBENCH discovery differs from QEC export')
    comparison = {}
    original_output, root = Path(summary['output_directory']), Path(summary['qec_root'])
    for action, label in ((ACTIONS[0], 'ququart'), (ACTIONS[2], 'qutrit')):
        manifests = [report(directory / 'artifacts' / mode / label, action, lock) for mode in MODES]
        if any(value != manifests[0] for value in manifests[1:]):
            raise ValueError('Direct/CLI/browser scientific artifacts differ: ' + label)
        reports = [directory / 'artifacts' / mode / label for mode in MODES]
        if any((other / path.name).read_bytes() != path.read_bytes() for path in reports[0].iterdir() for other in reports[1:]):
            raise ValueError('Artifact bytes differ: ' + label)
        comparison[label] = {'byte_identical': True, 'artifact_count_per_mode': len(manifests[0]['files']) + 1,
                             'manifest_sha256': manifests[0]['sha256'], 'normalized_fields': []}
    receipts = [read_json(directory / 'validation' / (mode + '.json')) for mode in MODES]
    for receipt in receipts:
        verify_validation(receipt, directory / 'artifacts/direct/ququart')
    receipt_bytes = [(directory / 'validation' / (mode + '.json')).read_bytes() for mode in MODES]
    if any(value != receipts[0] for value in receipts[1:]) or any(value != receipt_bytes[0] for value in receipt_bytes[1:]):
        raise ValueError('Direct/CLI/browser validation receipts differ')
    comparison['validation'] = {'byte_identical': True, 'receipt_sha256': receipts[0]['sha256']}
    for mode in MODES:
        for action in ACTIONS:
            label = action.removeprefix('qec.').replace('.', '-')
            if mode != 'browser':
                command = read_json(directory / f'commands/{mode}-{label}.json')
                if command['exit_code'] != 0:
                    raise ValueError('Acceptance execution failed')
                if mode == 'direct':
                    params = parameters(original_output, root, mode, action, lock)
                    if (command.get('argv') != direct_argv(environment['executable'], action, params) or
                            command.get('cwd') != str(root) or
                            command.get('stdout') != f'commands/direct-{label}.stdout' or
                            command.get('stderr') != f'commands/direct-{label}.stderr'):
                        raise ValueError('Direct command argv/cwd or transcript differs from locked invocation')
                returned = read_json(directory / command['stdout'])
            if mode != 'direct':
                record = read_json(directory / f'runs/{mode}-{label}.json')
                verify_record(record, action, parameters(original_output, root, mode, action, lock), environment, source)
                if read_json(directory / 'store' / (record['id'] + '.json')) != record:
                    raise ValueError('Exported record differs from persisted snapshot')
                if record['capability']['backend']['descriptor_sha256'] != digest(descriptor):
                    raise ValueError('Run descriptor differs from retained backend export')
                if mode == 'cli' and record != returned:
                    raise ValueError('CLI output differs from saved run')
                returned = record['result']
            expected = receipts[0] if action == ACTIONS[1] else report(
                directory / 'artifacts' / mode / ('ququart' if action == ACTIONS[0] else 'qutrit'), action, lock)
            if returned != expected:
                raise ValueError('Command output differs from artifacts or validation receipt')
    browser = read_json(directory / 'browser.json')
    if (browser.get('status') != 'passed' or browser.get('exceptions') or
            not browser.get('engine', '').startswith(('Chromium ', 'Google Chrome ')) or
            [run['action'] for run in browser['runs']] != list(ACTIONS)):
        raise ValueError('Missing real-browser evidence')
    for run, action in zip(browser['runs'], ACTIONS):
        record = read_json(directory / ('runs/browser-' + action[4:].replace('.', '-') + '.json'))
        prefix = 'Validation passed' if action == ACTIONS[1] else 'Artifact manifest (backend-reported)'
        if (run['id'] != record['id'] or run['parameters'] != record['parameters'] or
                run['status'] != 'succeeded' or run['schema_sha256'] != record['capability']['schema_sha256'] or
                run['view']['hidden'] or not run['view']['text'].startswith(prefix)):
            raise ValueError('Browser receipt or structured view differs from saved run')
        if action != ACTIONS[1] and any(name not in run['view']['text'] or checksum not in run['view']['text']
                                       for name, checksum in record['result']['files'].items()):
            raise ValueError('Browser artifact view omits backend names/hashes')
    for name in ('pip-check', 'browser', 'contract-tests', 'browser-tests'):
        if read_json(directory / f'commands/{name}.json')['exit_code'] != 0:
            raise ValueError('Required acceptance check failed: ' + name)
    contract_text = (directory / 'commands/contract-tests.stderr').read_text()
    if 'Ran 8 tests' not in contract_text or not contract_text.rstrip().endswith('OK'):
        raise ValueError('Missing refresh/stale/unsupported descriptor regression transcript')
    if summary.get('comparison') != comparison:
        raise ValueError('Stored comparison differs from retained scientific evidence')
    return comparison


def run_acceptance(args):
    lock = read_json(LOCK)
    output, root = Path(args.output).resolve(), Path(args.qec_root).resolve()
    output.mkdir(parents=True, exist_ok=False)
    python = os.path.abspath(Path(args.python).expanduser())
    env = {key: value for key, value in os.environ.items() if key not in ('PYTHONPATH', 'PYTHONHOME')}
    summary = {'protocol': 'qsol-workbench-p2/1', 'status': 'running', 'qec_commit': lock['commit'],
               'modes': list(MODES), 'output_directory': str(output), 'qec_root': str(root),
               'started_at': datetime.now(timezone.utc).isoformat(), 'claim_scope': lock['claim_scope']}
    write_json(output / 'lock.json', lock)

    def capture(name, argv, cwd=root, command_env=env):
        started = time.monotonic()
        completed = subprocess.run(argv, cwd=cwd, env=command_env, capture_output=True,
                                   text=True, timeout=args.timeout + 15)
        (output / 'commands').mkdir(exist_ok=True)
        for stream in ('stdout', 'stderr'):
            (output / f'commands/{name}.{stream}').write_text(getattr(completed, stream), encoding='utf-8')
        write_json(output / f'commands/{name}.json', {'argv': argv, 'cwd': str(cwd), 'exit_code': completed.returncode,
                   'duration_seconds': round(time.monotonic() - started, 4),
                   'stdout': f'commands/{name}.stdout', 'stderr': f'commands/{name}.stderr'})
        if completed.returncode:
            raise ValueError(f'{name} failed: {completed.stderr[-1000:]}')
        return completed.stdout

    try:
        if capture('source-head', ['git', 'rev-parse', 'HEAD']).strip() != lock['commit']:
            raise ValueError('QEC checkout differs from pinned companion commit')
        if capture('source-status', ['git', 'status', '--porcelain', '--untracked-files=all']).strip():
            raise ValueError('QEC checkout is dirty')
        tracked = capture('source-files', ['git', 'ls-files', 'src/qec'])
        hashes = {str(Path(name).relative_to('src/qec')): sha256(root / name)
                  for name in tracked.splitlines() if name.endswith('.py')}
        verify_source_map(hashes, lock)
        code = """import hashlib,importlib.metadata as m,json,platform,sys
import qec
from pathlib import Path
root=Path(qec.__file__).parent
packages={name:{'version':m.version(name)} for name in ('qec','numpy','scipy')}
print(json.dumps({'executable':sys.executable,'python':sys.version,'prefix':sys.prefix,'base_prefix':sys.base_prefix,
 'platform':platform.platform(),'architecture':platform.machine(),'packages':packages,
 'module_files':{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*.py'))}}))
"""
        environment = json_loads(capture('environment', [python, '-c', code]))
        installed = environment.pop('module_files')
        verify_environment(environment, lock)
        if installed != hashes or environment['executable'] != python or environment['prefix'] == environment['base_prefix']:
            raise ValueError('Install the pinned QEC wheel in a separate venv')
        write_json(output / 'environment.json', environment)
        write_json(output / 'qec-source.json', {'commit': lock['commit'], 'installed_matches_source': True, 'python_files': hashes})
        capture('pip-check', [python, '-m', 'pip', 'check'])
        capture('pip-freeze', [python, '-m', 'pip', 'freeze', '--all'])
        descriptor = json_loads(capture('descriptor', [python, '-m', 'qec.capabilities']))
        write_json(output / 'descriptor.json', descriptor)
        write_json(output / 'workbench-source.json', {'files': {p.relative_to(ROOT).as_posix(): sha256(p)
            for p in sorted((ROOT / 'src/qsol_workbench').rglob('*')) if p.is_file() and p.suffix in ('.py', '.js', '.html', '.css')}})
        # Fixture proofs are retained separately from the real scientific runs.
        capture('contract-tests', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_qec_descriptors.py', '-v'], ROOT)
        capture('browser-tests', ['node', '--test', 'tests/browser_values.mjs'], ROOT)
        config = {'demo': {'enabled': False}, 'qec': {'enabled': True, 'discovery': 'descriptor', 'python': python, 'cwd': str(root)}}
        write_json(output / 'config.json', config)
        (output / 'runs').mkdir()
        (output / 'validation').mkdir()
        runtime, server = Runtime(config, output / 'store', timeout=args.timeout), None
        try:
            if set(runtime.actions) != set(ACTIONS):
                raise ValueError('Real descriptor discovery failed: ' + json.dumps(runtime.connections))
            write_json(output / 'discovery.json', runtime.manifest())
            cases = []
            for mode in MODES:
                for action, module in zip(ACTIONS, MODULES):
                    params = parameters(output, root, mode, action, lock)
                    label = action[4:].replace('.', '-')
                    if mode == 'browser':
                        cases.append({'name': label, 'action': action, 'parameters': params, 'status': 'succeeded',
                                      'view': 'Validation passed' if action == ACTIONS[1] else 'Artifact manifest (backend-reported)',
                                      'record': str(output / f'runs/browser-{label}.json')})
                        continue
                    argv = direct_argv(python, action, params)
                    if mode == 'cli':
                        argv = [sys.executable, str(ROOT / 'workbench.py'), '--config', str(output / 'config.json'),
                                '--store', str(output / 'store'), '--timeout', str(args.timeout), 'run', action, '--params', json.dumps(params)]
                    result = json_loads(capture(mode + '-' + label, argv, ROOT if mode == 'cli' else root))
                    if mode == 'cli':
                        write_json(output / f'runs/cli-{label}.json', result)
            write_json(output / 'browser-cases.json', cases)
            server = make_server(runtime, port=0)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            browser_env = {**env, 'BROWSER_BIN': args.browser_bin,
                           'WORKBENCH_URL': f'http://127.0.0.1:{server.server_port}/#token={server.workbench_token}'}
            capture('browser', ['node', str(ROOT / 'tools/qec_browser.mjs'), str(output / 'browser-cases.json'),
                                str(output / 'browser.json'), str(args.timeout)], ROOT, browser_env)
        finally:
            if server:
                server.shutdown(); server.server_close()
            runtime.close()
        summary['comparison'] = {}
        for action, label in ((ACTIONS[0], 'ququart'), (ACTIONS[2], 'qutrit')):
            manifests = [report(output / 'artifacts' / mode / label, action, lock) for mode in MODES]
            if any(value != manifests[0] for value in manifests[1:]):
                raise ValueError('Scientific artifacts differ: ' + label)
            summary['comparison'][label] = {'byte_identical': True, 'artifact_count_per_mode': len(manifests[0]['files']) + 1,
                                            'manifest_sha256': manifests[0]['sha256'], 'normalized_fields': []}
        receipt = read_json(output / 'validation/direct.json')
        summary['comparison']['validation'] = {'byte_identical': True, 'receipt_sha256': receipt['sha256']}
        summary['status'] = 'passed'
    except Exception as error:
        summary.update(status='failed', error=f'{type(error).__name__}: {error}')
    finally:
        summary['finished_at'] = datetime.now(timezone.utc).isoformat()
        write_json(output / 'summary.json', summary)
        seal(output)
    try:
        if summary['status'] != 'passed':
            raise ValueError(summary['error'])
        verify_evidence(output)
    except Exception as error:
        summary.update(status='failed', error=f'{type(error).__name__}: {error}')
        write_json(output / 'summary.json', summary)
        seal(output)
        raise
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify')
    parser.add_argument('--qec-root')
    parser.add_argument('--python')
    parser.add_argument('--output')
    parser.add_argument('--browser-bin', default=os.environ.get('BROWSER_BIN', 'google-chrome'))
    parser.add_argument('--timeout', type=float, default=180)
    args = parser.parse_args()
    try:
        if args.verify:
            result = verify_evidence(args.verify)
        else:
            if not args.qec_root or not args.python or not args.output:
                parser.error('--qec-root, --python and a fresh --output are required')
            if not 0 < args.timeout <= 86400:
                parser.error('--timeout must be between 0 and 86400 seconds')
            result = run_acceptance(args)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print('P2 acceptance error: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
