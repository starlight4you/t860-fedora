#!/usr/bin/env python3
"""Read-only KWin CPU / DRM engine / GPU frequency samples; run on the tablet.

Compare an idle capture with one taken while dragging a window. CPU percent
uses 100% for one CPU core. DRM engine deltas describe KWin's submitted work,
not total GPU occupancy or displayed FPS. No tracing or power settings change.
"""
import argparse
import json
import os
from pathlib import Path
import time


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def snapshot():
    processes = {}
    for proc in Path('/proc').glob('[0-9]*'):
        if read(proc / 'comm') != 'kwin_wayland':
            continue
        stat = read(proc / 'stat')
        if not stat:
            continue
        fields = stat.rpartition(')')[2].split()
        clients = {}
        errors = []
        try:
            for fd in (proc / 'fdinfo').iterdir():
                info = read(fd)
                if info is None:
                    errors.append(f'cannot read {fd}')
                    continue
                data = dict(line.split(':', 1) for line in info.splitlines() if ':' in line)
                if data.get('drm-driver', '').strip() != 'msm':
                    continue
                client = data.get('drm-client-id', '').strip()
                engine = data.get('drm-engine-gpu', '').split()
                if client and engine:
                    # dup() descriptors share counters: count each client once.
                    clients[client] = int(engine[0])
        except OSError as exc:
            errors.append(str(exc))
        processes[proc.name] = {
            'start': fields[19],
            'cpu_ticks': int(fields[11]) + int(fields[12]),
            'clients_ns': clients,
            'read_errors': errors,
        }
    irq = {}
    for line in (read('/proc/interrupts') or '').splitlines():
        parts = line.split()
        if parts and parts[-1] in ('gpu-irq', 'gmu'):
            counts = []
            for value in parts[1:]:
                if not value.isdecimal():
                    break
                counts.append(int(value))
            irq[parts[-1]] = sum(counts)
    devices = []
    for path in Path('/sys/class/devfreq').glob('*gpu*'):
        device = path.resolve().parent.parent
        devices.append({
            'name': path.name,
            'frequency_hz': read(path / 'cur_freq'),
            'governor': read(path / 'governor'),
            'runtime_status': read(device / 'power/runtime_status'),
        })
    return {'time': time.monotonic(), 'kwin': processes, 'irq': irq, 'gpu': devices}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=float, default=15)
    parser.add_argument('--interval', type=float, default=1)
    args = parser.parse_args()
    if args.seconds <= 0 or args.interval <= 0:
        parser.error('--seconds and --interval must be positive')
    if not Path('/proc/self/stat').exists():
        parser.error('run on the Linux tablet, not the macOS host')
    print(json.dumps({'kernel': os.uname().release,
                      'boot_id': read('/proc/sys/kernel/random/boot_id'),
                      'cpu_percent_unit': '100% = one CPU core',
                      'note': 'DRM engine time is not displayed FPS'}, ensure_ascii=False), flush=True)
    previous = snapshot()
    deadline = previous['time'] + args.seconds
    ticks = os.sysconf('SC_CLK_TCK')
    while previous['time'] < deadline:
        time.sleep(min(args.interval, max(0, deadline - previous['time'])))
        current = snapshot()
        elapsed = current['time'] - previous['time']
        output = {'interval_s': round(elapsed, 3), 'kwin': {}, 'gpu': current['gpu']}
        for pid, values in current['kwin'].items():
            result = {'msm_clients': len(values['clients_ns']),
                      'read_errors': values['read_errors']}
            before = previous['kwin'].get(pid)
            if before and before['start'] == values['start']:
                result['cpu_percent'] = round(100 * (values['cpu_ticks'] - before['cpu_ticks']) / ticks / elapsed, 2)
                result['engine_ms'] = round(sum(max(0, value - before['clients_ns'][client])
                    for client, value in values['clients_ns'].items()
                    if client in before['clients_ns']) / 1e6, 3)
            output['kwin'][pid] = result
        output['irq_per_s'] = {key: round((value - previous['irq'][key]) / elapsed, 2)
                               for key, value in current['irq'].items() if key in previous['irq']}
        print(json.dumps(output, ensure_ascii=False), flush=True)
        previous = current


if __name__ == '__main__':
    main()
