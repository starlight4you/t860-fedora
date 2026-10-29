#!/usr/bin/env python3
"""Trace DRM commit latency and CPU blits during a command.

Requires root, ftrace/function_graph and kprobe_events on arm64. Uses a private
trace instance and probe group, and removes both on exit. Does not measure the
physical panel refresh rate. Example:
  tabs6-gpu-trace.py --output /tmp/gpu-output.trace -- sleep 12
"""
import argparse
from pathlib import Path
import os
import signal
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command[:1] == ['--']:
        command = command[1:]
    if not command:
        parser.error('supply a bounded command after --')
    if os.geteuid() != 0:
        parser.error('requires root')

    root = Path('/sys/kernel/tracing')
    if not (root / 'kprobe_events').exists():
        root = Path('/sys/kernel/debug/tracing')
    if not (root / 'kprobe_events').exists():
        parser.error('tracefs and CONFIG_KPROBE_EVENTS are required')
    name = f'tabs6_gpu_{os.getpid()}'
    instance = root / 'instances' / name
    instance.mkdir()
    probe_added = False
    child = None
    recording = False

    def write(path, value):
        path.write_text(str(value) + '\n')

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    def probe_command(value):
        # Text append mode may seek, which tracefs rejects with EINVAL.
        fd = os.open(root / 'kprobe_events', os.O_WRONLY | os.O_APPEND)
        try:
            os.write(fd, value.encode())
        finally:
            os.close(fd)

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, interrupted)
    try:
        write(instance / 'tracing_on', 0)
        write(instance / 'buffer_size_kb', 1024)
        write(instance / 'trace_clock', 'mono')
        # 6.12 exposes graph-root/depth controls only on the global instance.
        # A private function filter avoids changing those shared controls.
        available = {line.split()[0] for line in
                     (root / 'available_filter_functions').read_text().splitlines()
                     if line.split()}
        requested = (
            'simpledrm_primary_plane_helper_atomic_update',
            'drm_gem_fb_begin_cpu_access', 'drm_gem_fb_end_cpu_access',
            'drm_fb_blit', 'drm_atomic_helper_wait_for_fences',
            'drm_atomic_helper_commit_tail', 'msm_atomic_commit_tail',
            'drm_atomic_helper_wait_for_vblanks',
            'drm_atomic_helper_wait_for_flip_done')
        # Native MSM removes simpledrm, so its function may no longer exist.
        # Writing a missing symbol rejects the entire ftrace filter.
        selected = [name for name in requested if name in available]
        if 'drm_fb_blit' not in available:
            raise RuntimeError('drm_fb_blit is unavailable; cannot trace CPU blits')
        write(instance / 'set_ftrace_filter', '\n'.join(selected))
        print('Tracing functions: ' + ', '.join(selected), flush=True)
        write(instance / 'current_tracer', 'function_graph')
        for option in ('funcgraph-abstime', 'funcgraph-proc', 'funcgraph-duration',
                       'funcgraph-tail', 'sleep-time'):
            path = instance / 'options' / option
            if path.exists():
                write(path, 1)
        # drm_fb_blit arg5 is struct drm_rect *clip on the arm64 ABI.
        probe_command(f'p:{name}/blit drm_fb_blit '
                      'x1=+0(%x5):s32 y1=+4(%x5):s32 '
                      'x2=+8(%x5):s32 y2=+12(%x5):s32 dst_format=%x2:u32\n')
        probe_added = True
        write(instance / 'events' / name / 'blit' / 'enable', 1)
        write(instance / 'trace', '')
        write(instance / 'tracing_on', 1)
        recording = True
        child = subprocess.Popen(command)
        status = child.wait()
        write(instance / 'tracing_on', 0)
        recording = False
        args.output.write_text(instance.joinpath('trace').read_text())
        print(f'Trace saved to {args.output}; child status={status}', flush=True)
        return status
    finally:
        if child and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        if recording:
            write(instance / 'tracing_on', 0)
        # Reset only the instance and probe created by this process.
        if probe_added:
            write(instance / 'events' / name / 'blit' / 'enable', 0)
        write(instance / 'current_tracer', 'nop')
        instance.rmdir()
        if probe_added:
            probe_command(f'-:{name}/blit\n')


if __name__ == '__main__':
    raise SystemExit(main())
