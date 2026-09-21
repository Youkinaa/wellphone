#!/usr/bin/env python3
"""Synthetic API34 concurrency experiment; NEVER evidence of a human/pinyin test."""
import argparse
import json
import re
import signal
import shlex
import subprocess
import threading
import time
import traceback
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from scrcpy_probe import ScrcpyProbe

MAIN, AGENT = 'com.wellphone.probe.main', 'com.wellphone.probe.agent'
KEYS = [('ni', 180, 1015), ('nihao', 540, 1015), ('commit_chinese', 180, 1090), ('commit_ascii', 540, 1090)]


class Run:
    def __init__(self, args):
        self.args, self.phase, self.sid, self.probe = args, 'setup', None, None
        self.out = Path(args.output); self.out.mkdir(parents=True, exist_ok=False)
        self.lock, self.stop = threading.RLock(), threading.Event()
        self.latest, self.fixture_events, self.failures = {}, [], []
        self.log = (self.out / 'events.jsonl').open('x', encoding='utf-8')
        self.raw = (self.out / 'fixtures.log').open('x', encoding='utf-8')
        self.logcat = self.reader = self.monitor = None
        self.summary = {'input_kind': 'synthetic ProbeIME + adb input -d 0, not human/pinyin',
                        'limits': ['standard EditText fixtures only', 'original Appium server: startup Toast capture and no device-side guard/Enter patches',
                                   'sampled dumpsys cannot exclude all transient system changes'], 'phases': [], 'output': str(self.out)}

    def event(self, kind, **data):
        with self.lock:
            row = dict(kind=kind, phase=self.phase, host_ns=time.monotonic_ns(), wall_ns=time.time_ns(), **data)
            self.log.write(json.dumps(row, ensure_ascii=False) + '\n'); self.log.flush()
            return row

    def adb(self, *args, timeout=10):
        start = time.monotonic_ns()
        try:
            p = subprocess.run([self.args.adb, '-s', self.args.serial, *map(str, args)], capture_output=True, text=True, timeout=timeout)
            self.event('adb', args=args, started_ns=start, elapsed_ms=(time.monotonic_ns()-start)/1e6,
                       returncode=p.returncode, stderr=p.stderr)
            if p.returncode: raise RuntimeError(f'ADB {args}: {p.stderr} {p.stdout}')
            return p.stdout
        except BaseException as exc:
            self.event('adb_failure', args=args, error=repr(exc)); raise

    def http(self, method, path, body=None, timeout=25):
        start = time.monotonic_ns(); raw = ''; status = None
        req = urllib.request.Request(self.args.appium_url.rstrip('/') + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'}, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                status, raw = response.status, response.read().decode()
            data = json.loads(raw)
            if isinstance(data.get('value'), dict) and 'error' in data['value']: raise RuntimeError(raw)
            return data['value']
        except urllib.error.HTTPError as exc:
            status, raw = exc.code, exc.read().decode(errors='replace'); raise RuntimeError(raw) from exc
        finally:
            self.event('http', method=method, path=path, request=body, response=raw, status=status,
                       started_ns=start, elapsed_ms=(time.monotonic_ns()-start)/1e6)

    def api(self, method, suffix, body=None):
        if not self.sid: raise RuntimeError('No owned session')
        return self.http(method, f'/session/{self.sid}{suffix}', body)

    def read_logs(self):
        try:
            for line in self.logcat.stdout:
                self.raw.write(line); self.raw.flush()
                if '{' not in line: continue
                try: value = json.loads(line[line.index('{'):])
                except ValueError: continue
                key = 'ime' if 'WellphoneProbeIME' in line else value.get('package')
                if key not in ('ime', MAIN, AGENT): continue
                row = self.event('fixture', fixture=key, value=value)
                with self.lock:
                    self.latest[key] = value; self.fixture_events.append(row)
        except BaseException as exc:
            self.failures.append('Log reader: ' + repr(exc))

    def wait_state(self, key, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock: state = dict(self.latest.get(key, {}))
            if state and predicate(state): return state
            if self.logcat.poll() is not None: raise RuntimeError('Filtered logcat ended')
            time.sleep(.03)
        raise RuntimeError(f'No expected {key} state: {state}')

    def tap_main(self, name, x, y):
        with self.lock:
            old = dict(self.latest.get(MAIN, {})); ime_seq = self.latest.get('ime', {}).get('seq', -1)
        self.event('main_action_start', action=name, x=x, y=y)
        self.adb('shell', 'input', '-d', '0', 'tap', x, y)
        self.event('main_action_end', action=name)
        time.sleep(self.args.interval)
        values = {'ni': 'ni', 'nihao': 'nihao', 'commit_chinese': '你好', 'commit_ascii': 'A'}
        if name in values:
            text, composing = values[name], name in ('ni', 'nihao')
            start = old['composing_start'] if old['composing_start'] >= 0 else old['selection_start']
            end = old['composing_end'] if old['composing_end'] >= 0 else old['selection_end']
            expected = old['text'][:start] + text + old['text'][end:]; cursor = start + len(text)
            ime = self.wait_state('ime', lambda s: s['seq'] > ime_seq and s.get('synthetic_text') == text
                                  and s.get('result') is True and s['target_package'] == MAIN
                                  and s['event'] == ('set_composing_text' if composing else 'commit_text'))
            state = self.wait_state(MAIN, lambda s: s['seq'] > old['seq'] and s['text'] == expected
                                    and s['selection_start'] == s['selection_end'] == cursor
                                    and (s['composing_start'], s['composing_end']) == ((start, cursor) if composing else (-1, -1)))
            self.event('main_action_verified', action=name, ime=ime, state=state)

    def snapshot(self):
        with self.lock: seq = self.latest.get(MAIN, {}).get('seq', -1)
        self.tap_main('readback', 360, 471)
        main = self.wait_state(MAIN, lambda s: s['seq'] > seq and s['event'] == 'readback')
        with self.lock: seq = self.latest.get('ime', {}).get('seq', -1)
        self.tap_main('ime_snapshot', 540, 1170)
        ime = self.wait_state('ime', lambda s: s['seq'] > seq and s['event'] == 'snapshot')
        return {'main': main, 'ime': ime}

    def metadata(self):
        number = 0
        while not self.stop.is_set():
            try:
                for service in ('window', 'input_method'):
                    content = self.adb('shell', 'dumpsys', service)
                    (self.out / f'meta-{number:04d}-{service}.txt').write_text(content)
                self.event('metadata', sample=number); number += 1
            except BaseException as exc:
                self.failures.append('Metadata: ' + repr(exc)); return
            self.stop.wait(2)

    def check_main(self, before, after, expected, since):
        main, old, ime = after['main'], before['main'], after['ime']
        checks = {'main_text_exact': main['text'] == expected, 'main_display_0': main['display_id'] == 0,
                  'main_instance_unchanged': all(main[k] == old[k] for k in ('pid', 'instance')),
                  'main_focused': main['window_focus'] and main['editor_focus'],
                  'no_window_focus_loss': main['window_focus_lost'] == old['window_focus_lost'],
                  'no_input_connection_recreation': main['input_connections'] == old['input_connections'],
                  'ime_target_main': ime['target_package'] == MAIN,
                  'ime_session_unchanged': all(ime[k] == before['ime'][k] for k in ('pid', 'instance', 'field_id', 'input_starts', 'input_finishes', 'view_starts', 'view_finishes'))}
        with self.lock: events = [r for r in self.fixture_events if r['host_ns'] >= since]
        checks['no_ime_rejection_or_switch'] = all(r['value'].get('result') is not False and r['value'].get('target_package') == MAIN
                                                    for r in events if r['fixture'] == 'ime')
        checks['main_continuous_focus_and_instance'] = all(all(r['value'].get(k) == old[k] for k in ('pid', 'instance', 'input_connections', 'window_focus_lost'))
                  and all(r['value'].get(k) for k in ('window_focus', 'editor_focus', 'resumed', 'ime_visible')) for r in events if r['fixture'] == MAIN)
        checks['ime_continuous_session'] = all(all(r['value'].get(k) == before['ime'][k] for k in ('pid', 'instance', 'field_id', 'input_starts', 'input_finishes', 'view_starts', 'view_finishes'))
                                                 for r in events if r['fixture'] == 'ime')
        self.event('main_checks', checks=checks, expected=expected, before=before, after=after)
        if not all(checks.values()): raise AssertionError(f'Main input checks failed: {checks}')
        return checks

    def agent_round(self, label, tap_counter):
        source = self.api('GET', '/source')
        (self.out / f'source-{label}.xml').write_text(source)
        if MAIN in source or AGENT not in source: raise AssertionError('Source display/package scope mismatch')
        def find(name):
            value = self.api('POST', '/element', {'using': 'id', 'value': f'{AGENT}:id/{name}'})
            return value.get('element-6066-11e4-a52e-4f735466cecf') or value['ELEMENT']
        element = find('probe_editor'); expected = f'副屏-中文-😀-{label}'
        self.api('POST', '/execute/sync', {'script': 'mobile: replaceElementValue', 'args': [{'elementId': element, 'text': expected}]})
        actual = self.api('GET', f'/element/{find("probe_editor")}/text')
        self.event('agent_readback', label=label, expected=expected, actual=actual)
        if actual != expected: raise AssertionError('Agent Chinese readback mismatch')
        if tap_counter:
            node = next(n for n in ET.fromstring(source).iter() if n.get('resource-id') == f'{AGENT}:id/probe_counter')
            x1, y1, x2, y2 = map(int, re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', node.get('bounds')).groups())
            with self.lock: old = self.latest.get(AGENT, {}).get('counter', 0)
            self.probe.tap((x1+x2)//2, (y1+y2)//2)
            self.wait_state(AGENT, lambda s: s['counter'] == old+1 and s['display_id'] == self.probe.display_id)
            self.event('agent_counter', expected=old+1)

    def input_loop(self, end, counts):
        try:
            while not end.is_set():
                self.event('input_cycle_start', cycle=counts['complete']+1)
                for key in KEYS: self.tap_main(*key)
                counts['complete'] += 1
                self.event('input_cycle_end', cycle=counts['complete'])
        except BaseException as exc:
            counts['error'] = repr(exc); end.set()

    def phase_run(self, name, concurrent):
        self.phase = name; before = self.snapshot(); start = time.monotonic_ns()
        end, counts = threading.Event(), {'complete': 0}; rounds = 0
        worker = threading.Thread(target=self.input_loop, args=(end, counts), daemon=True)
        worker.start(); deadline = time.monotonic() + self.args.seconds; last_print = 0
        record = {'name': name, 'requested_seconds': self.args.seconds, 'started_ns': start}
        try:
            while time.monotonic() < deadline and not self.stop.is_set():
                if counts.get('error') or self.failures: raise RuntimeError(str(counts) + str(self.failures))
                if concurrent: self.agent_round(f'{name}-{rounds:04d}', True); rounds += 1
                else: time.sleep(.1)
                if time.monotonic()-last_print >= 10:
                    print(json.dumps({'phase': name, 'input_cycles': counts['complete'], 'agent_rounds': rounds}), flush=True)
                    last_print = time.monotonic()
            if self.stop.is_set(): raise InterruptedError('Stop requested')
        finally:
            end.set(); worker.join(45)
            record.update(completed_cycles=counts['complete'], agent_rounds=rounds, elapsed_seconds=(time.monotonic_ns()-start)/1e9, input_error=counts.get('error'))
            self.summary['phases'].append(record)
            if worker.is_alive(): raise RuntimeError('Input worker did not stop at cycle boundary')
        if counts.get('error'): raise RuntimeError(counts['error'])
        if counts['complete'] == 0 or (concurrent and rounds == 0): raise AssertionError('Empty measurement phase')
        after = self.snapshot(); expected = before['main']['text'] + '你好A'*counts['complete']
        record['checks'] = self.check_main(before, after, expected, start)
        if after['main']['composing_start'] != -1: raise AssertionError('Unexpected unfinished composition')

    def execute(self):
        self.logcat = subprocess.Popen([self.args.adb, '-s', self.args.serial, 'logcat', '-v', 'threadtime', '-T', '1', 'WellphoneProbe:I', 'WellphoneProbeIME:I', '*:S'],
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        self.reader = threading.Thread(target=self.read_logs, daemon=True); self.reader.start()
        self.monitor = threading.Thread(target=self.metadata, daemon=True); self.monitor.start()
        before = self.snapshot(); initial = before['main']['text']; since = time.monotonic_ns()
        experiment_before, experiment_since = before, since
        if before['main']['composing_start'] != -1 or before['main']['selection_end'] != len(initial):
            raise RuntimeError('Prepare main editor without composition and selection at end')
        self.tap_main(*KEYS[0])
        held = self.wait_state(MAIN, lambda s: s['text'] == initial+'ni' and s['composing_start'] >= 0)
        self.event('held_composition', state=held)
        self.probe = ScrcpyProbe(adb=self.args.adb, serial=self.args.serial, server=self.args.scrcpy_server, output=self.out/'scrcpy', save_video=True)
        self.probe.start(); self.summary['display_id'] = self.probe.display_id
        launch = self.adb('shell', 'am', 'start', '--display', self.probe.display_id, '-n', AGENT+'/com.wellphone.probe.ProbeActivity')
        (self.out/'agent-launch.txt').write_text(launch)
        self.wait_state(AGENT, lambda s: s['display_id'] == self.probe.display_id and s['resumed'])
        display = self.adb('shell', 'dumpsys', 'display'); (self.out/'display.txt').write_text(display)
        infos = [line for line in display.splitlines() if 'DisplayInfo{' in line and re.search(r'\bdisplayId[ =]+'+str(self.probe.display_id)+r'\b', line)]
        flag_data = json.loads(self.adb('shell', 'CLASSPATH='+shlex.quote(self.args.flags_classpath)+' app_process / DisplayFlags '+str(self.probe.display_id)))
        (self.out/'display-flags.json').write_text(json.dumps(flag_data)+'\n')
        flags = flag_data['flags']
        if not infos or flag_data['display_id'] != self.probe.display_id or flags & 0x1880 != 0x1880 or flags & 4:
            raise AssertionError(f'Effective secondary display flags unverified: {flag_data}')
        self.summary['display_flags'] = flag_data
        self.summary['display_info'] = infos
        (self.out/'activity-activities.txt').write_text(self.adb('shell', 'dumpsys', 'activity', 'activities'))
        caps = {'platformName': 'Android', 'appium:automationName': 'UiAutomator2', 'appium:udid': self.args.serial, 'appium:newCommandTimeout': 180,
                **{f'appium:{k}': v for k,v in dict(skipDeviceInitialization=True, autoLaunch=False, noReset=True, skipUnlock=True, skipLogcatCapture=True, disableSuppressAccessibilityService=True).items()}}
        created = self.http('POST', '/session', {'capabilities': {'alwaysMatch': caps}}, timeout=90)
        self.sid = created['sessionId']; self.summary['session_id'] = self.sid
        settings = dict(currentDisplayId=self.probe.display_id, enableMultiWindows=True, enableNotificationListener=False, waitForIdleTimeout=0)
        self.api('POST', '/appium/settings', {'settings': settings})
        actual = self.api('GET', '/appium/settings'); self.summary['settings'] = actual
        if any(actual.get(k) != v for k,v in settings.items()): raise AssertionError('Settings readback mismatch')
        time.sleep(3.6)  # Original Toast cache expiry; not a startup no-capture guarantee.
        self.agent_round('held-composition', False); after = self.snapshot()
        self.check_main(before, after, initial+'ni', since)
        if (after['main']['composing_start'], after['main']['composing_end']) != (held['composing_start'], held['composing_end']):
            raise AssertionError('Held composition range changed')
        for key in KEYS[1:]: self.tap_main(*key)
        self.wait_state(MAIN, lambda s: s['text'] == initial+'你好A' and s['composing_start'] == -1)
        self.phase_run('baseline', False); self.phase_run('concurrent', True)
        self.phase = 'idle-10000-comparison'; before = self.snapshot(); since = time.monotonic_ns()
        self.api('POST', '/appium/settings', {'settings': {'waitForIdleTimeout': 10000}})
        end, counts = threading.Event(), {'complete': 0}
        worker = threading.Thread(target=self.input_loop, args=(end, counts), daemon=True); worker.start()
        record = {'name': self.phase, 'http_timeout_seconds': 15}; start = time.monotonic()
        try:
            time.sleep(.6)
            source = self.http('GET', f'/session/{self.sid}/source', timeout=15)
            (self.out/'source-idle-10000.xml').write_text(source)
            if MAIN in source or AGENT not in source: raise AssertionError('Default-idle source scope mismatch')
            record['source_returned'] = True
        except (TimeoutError, urllib.error.URLError) as exc:
            record['source_returned'] = False; record['request_error'] = repr(exc)
        finally:
            record['elapsed_seconds'] = time.monotonic()-start
            end.set(); worker.join(45); record['completed_cycles'] = counts['complete']
            self.summary['phases'].append(record)
            if worker.is_alive(): raise RuntimeError('Comparison input worker did not finish')
            self.api('POST', '/appium/settings', {'settings': {'waitForIdleTimeout': 0}})
        if counts.get('error'): raise RuntimeError(counts['error'])
        record['checks'] = self.check_main(before, self.snapshot(), before['main']['text']+'你好A'*counts['complete'], since)
        self.phase = 'cross-phase-continuity'
        expected = initial + '你好A'*(1+sum(p['completed_cycles'] for p in self.summary['phases']))
        self.summary['cross_phase_checks'] = self.check_main(experiment_before, self.snapshot(), expected, experiment_since)

    def close(self):
        self.phase = 'cleanup'; self.stop.set()
        for action in ([lambda: self.http('DELETE', f'/session/{self.sid}', timeout=15)] if self.sid else []) + ([self.probe.close] if self.probe else []):
            try: action()
            except BaseException as exc: self.failures.append('Cleanup: ' + repr(exc))
        if self.monitor:
            self.monitor.join(25)
            if self.monitor.is_alive():
                self.failures.append('Metadata worker failed to stop; preserving open logs')
        if self.logcat:
            self.logcat.terminate()
            try: self.logcat.wait(5)
            except subprocess.TimeoutExpired: self.logcat.kill(); self.logcat.wait(5)
        if self.reader:
            self.reader.join(5)
            if self.reader.is_alive(): self.failures.append('Log reader failed to stop; preserving open logs')
        self.summary['errors'] = self.failures
        self.summary['runner_completed'] = self.summary.get('runner_completed', False) and not self.failures
        (self.out/'summary.json').write_text(json.dumps(self.summary, ensure_ascii=False, indent=2)+'\n')
        if not self.reader or not self.reader.is_alive(): self.raw.close()
        if not any(t and t.is_alive() for t in (self.monitor, self.reader)): self.log.close()
        print(json.dumps(self.summary, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', required=True, help='Path to the adb executable')
    parser.add_argument('--serial', required=True, help='Dedicated test AVD serial')
    parser.add_argument('--appium-url', required=True, help='Appium server URL, including any base path')
    parser.add_argument('--scrcpy-server', required=True, help='Path to the patched scrcpy 4.1 server')
    parser.add_argument('--flags-classpath', default='/data/local/tmp/wellphone-display-flags.jar',
                        help='Device path to the pre-pushed DisplayFlags dex jar')
    parser.add_argument('--output', required=True, help='New directory for this run; must not exist')
    parser.add_argument('--seconds', type=float, default=60)
    parser.add_argument('--interval', type=float, default=.15)
    args = parser.parse_args()
    if args.seconds <= 0 or args.interval < .1: parser.error('seconds must be positive; interval >= .1')
    run = Run(args)
    for sig in (signal.SIGINT, signal.SIGTERM): signal.signal(sig, lambda *_: run.stop.set())
    try: run.execute(); run.summary['runner_completed'] = True
    except BaseException:
        run.failures.append(traceback.format_exc())
    finally: run.close()
    return 0 if run.summary['runner_completed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
