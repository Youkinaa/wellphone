"""Read-only evidence summary, not an execution harness or an acceptance verdict."""
import collections
import json
import statistics
import sys
from pathlib import Path

root = Path(sys.argv[1])
summary = json.loads((root / 'summary.json').read_text())
rows = [json.loads(line) for line in (root / 'events.jsonl').read_text().splitlines()]
main_name = 'com.wellphone.probe.main'
fixtures = [r for r in rows if r['kind'] == 'fixture']
checks = [r for r in rows if r['kind'] == 'main_checks']
report = {'runner_completed': summary.get('runner_completed'), 'errors': summary['errors'],
          'declared_scope': summary['input_kind'], 'phases': summary['phases'],
          'display_flags': summary.get('display_flags'), 'cross_phase_checks': summary.get('cross_phase_checks'),
          'http_requests': sum(r['kind'] == 'http' for r in rows), 'fixture_events': len(fixtures)}
report['reported_main_check_count'] = len(checks)
report['reported_main_check_failures'] = [r['checks'] for r in checks if not all(r['checks'].values())]
# Independently evaluate ALL measured phases, including setup and boundary snapshots.
if checks:
    first, last = checks[0]['before'], checks[-1]['after']
    selected = [r for r in fixtures if r['fixture'] in (main_name, 'ime')
                and first['main' if r['fixture'] == main_name else 'ime']['elapsed_ns'] <= r['value']['elapsed_ns']
                <= last['main' if r['fixture'] == main_name else 'ime']['elapsed_ns']]
    violations = []
    main_fields = ('pid', 'instance', 'display_id', 'input_connections', 'window_focus_lost')
    ime_fields = ('pid', 'instance', 'target_package', 'field_id', 'input_starts', 'input_finishes', 'view_starts', 'view_finishes')
    for row in selected:
        is_main = row['fixture'] == main_name
        before = first['main' if is_main else 'ime']; value = row['value']
        bad = [field for field in (main_fields if is_main else ime_fields) if value.get(field) != before.get(field)]
        if is_main:
            bad += [field for field in ('window_focus', 'editor_focus', 'resumed', 'ime_visible') if not value.get(field)]
        elif value.get('result') is False:
            bad.append('input_connection_result')
        if bad: violations.append({'fixture': row['fixture'], 'seq': value['seq'], 'event': value['event'], 'bad': bad})
    report['independent_continuity_violations'] = violations
    report['independent_continuity_events'] = len(selected)
    report['main_initial_final'] = {k: {'first': first['main'].get(k), 'last': last['main'].get(k)} for k in main_fields}
    report['ime_initial_final'] = {k: {'first': first['ime'].get(k), 'last': last['ime'].get(k)} for k in ime_fields}
else:
    report['independent_continuity_violations'] = 'Not evaluable: no completed endpoint check'
for kind in ('input_cycle_end', 'main_action_verified', 'agent_readback', 'agent_counter'):
    report[kind + '_counts'] = dict(collections.Counter(r['phase'] for r in rows if r['kind'] == kind))
input_windows = []
pending = {}
for row in rows:
    key = (row['phase'], row.get('cycle'))
    if row['kind'] == 'input_cycle_start': pending[key] = row['host_ns']
    elif row['kind'] == 'input_cycle_end' and key in pending:
        input_windows.append((row['phase'], pending.pop(key), row['host_ns']))
concurrent_writes = [r for r in rows if r['kind'] == 'agent_readback' and r['phase'] == 'concurrent']
report['interleaving'] = {
    'concurrent_agent_readbacks': len(concurrent_writes),
    'readbacks_inside_complete_main_cycles': sum(any(phase == 'concurrent' and start <= r['host_ns'] <= end
                                                    for phase, start, end in input_windows) for r in concurrent_writes),
    'complete_main_cycles_containing_agent_readback': sum(any(start <= r['host_ns'] <= end for r in concurrent_writes)
                                                        for phase, start, end in input_windows if phase == 'concurrent'),
    'readbacks_with_latest_logged_main_composition_active': 0,
    'timestamp_basis': 'host receive timestamps, not synchronized device/HTTP execution timestamps',
}
latest_main = None
for row in rows:
    if row['kind'] == 'fixture' and row['fixture'] == main_name: latest_main = row['value']
    elif row['kind'] == 'agent_readback' and row['phase'] == 'concurrent' and latest_main and latest_main['composing_start'] >= 0:
        report['interleaving']['readbacks_with_latest_logged_main_composition_active'] += 1
timings = collections.defaultdict(list)
for row in rows:
    if row['kind'] != 'http': continue
    path = row['path']; method = row['method']
    category = ('source' if path.endswith('/source') else 'find' if path.endswith('/element') else
                'replace' if path.endswith('/execute/sync') else 'readback' if path.endswith('/text') else 'other')
    timings[(row['phase'], category)].append(row['elapsed_ms'])
report['timings_ms'] = {}
for (phase, category), values in timings.items():
    ordered = sorted(values)
    report['timings_ms'][phase + '/' + category] = {'count': len(values), 'mean': round(statistics.mean(values), 2),
            'median': round(statistics.median(values), 2), 'min': round(min(values), 2), 'max': round(max(values), 2)}
sources = list(root.glob('source-*.xml'))
report['source_count'] = len(sources)
report['sources_containing_main_package'] = [p.name for p in sources if main_name in p.read_text()]
# Preserve exact focused-display/client evidence, grouped independently of the runner's checks.
fields = ('mTopFocusedDisplayId=', 'mCurClient=', 'mCurMethodId=', 'mCurTokenDisplayId=')
metadata = {field: collections.Counter() for field in fields}
for path in root.glob('meta-*.txt'):
    for line in path.read_text().splitlines():
        for field in fields:
            if field in line: metadata[field][line.strip()] += 1
report['metadata_values'] = {field: dict(values) for field, values in metadata.items()}
report['metadata_files'] = len(list(root.glob('meta-*.txt')))
print(json.dumps(report, ensure_ascii=False, indent=2))
