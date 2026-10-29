#!/usr/bin/env python3
"""Exercise libssc's real error callbacks with synchronous GTask completion.

Run on Linux with GCC/ASan and GLib development headers:
  python3 test-libssc-error-lifetime.py /path/to/libssc/src/libssc-sensor.c
No sensor hardware or QRTR support is needed.
"""
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile


PRELUDE = r'''
#include <gio/gio.h>
typedef GObject SSCClient;
static GMainLoop *loop;
static gboolean ssc_client_send_finish(SSCClient *self, GAsyncResult *result,
                                       GError **error) {
    g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_CLOSED,
                        "QRTR node was removed from the bus");
    return FALSE;
}
'''

HARNESS = r'''
static void complete(GObject *source, GAsyncResult *result, gpointer data) {
    GError *error = NULL;
    g_assert_false(g_task_propagate_boolean(G_TASK(result), &error));
    g_assert_error(error, G_IO_ERROR, G_IO_ERROR_CLOSED);
    g_clear_error(&error);
    g_main_loop_quit(loop);
}
static gboolean fail(gpointer task) {
    CALLBACK(NULL, NULL, task);
    return G_SOURCE_REMOVE;
}
static gboolean begin(gpointer data) {
    GTask *task = g_task_new(NULL, NULL, complete, NULL);
    /* Complete in the next iteration: GTask may call complete synchronously. */
    g_idle_add(fail, task);
    return G_SOURCE_REMOVE;
}
int main(void) {
    loop = g_main_loop_new(NULL, FALSE);
    g_idle_add(begin, NULL);
    g_main_loop_run(loop);
    g_main_loop_unref(loop);
    return 0;
}
'''


def main():
    source = Path(sys.argv[1]).read_text()
    flags = shlex.split(subprocess.check_output(
        ['pkg-config', '--cflags', '--libs', 'gio-2.0'], text=True))
    env = dict(os.environ, G_MESSAGES_DEBUG='all')
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for operation, verb in [('close', 'disable'), ('open', 'enable')]:
            callback = f'sensor_{operation}_ready'
            match = re.search(r'static void\n' + callback +
                              r' \(.*?\n}\n', source, re.S)
            if not match:
                raise RuntimeError(f'Cannot locate {callback}')
            fixed = match[0]
            log = f'\t\tg_debug ("Sensor {verb} request failed: %s", error->message);\n'
            if fixed.index(log) > fixed.index('g_task_return_error'):
                raise RuntimeError('Apply libssc-error-lifetime.patch first')
            original = fixed.replace(log, '').replace(
                '\t\tg_clear_object (&task);\n',
                '\t\tg_clear_object (&task);\n' + log)
            for label, body in [('fixed', fixed), ('original', original)]:
                c = root / f'{operation}-{label}.c'
                exe = c.with_suffix('')
                c.write_text(PRELUDE + body + HARNESS.replace('CALLBACK', callback))
                subprocess.run(['cc', '-g', '-O1', '-fsanitize=address', str(c),
                                '-o', str(exe), *flags], check=True)
                result = subprocess.run([str(exe)], env=env, capture_output=True,
                                        text=True, timeout=10)
                if label == 'fixed':
                    assert result.returncode == 0, result.stderr
                else:
                    assert result.returncode != 0, 'Original callback did not fail'
                    assert 'heap-use-after-free' in result.stderr, result.stderr
            print(f'{callback}: original UAF reproduced; fixed PASS')


if __name__ == '__main__':
    main()
