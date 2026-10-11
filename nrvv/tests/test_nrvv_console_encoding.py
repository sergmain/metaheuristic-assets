# The console a Function prints to (plan 045 Phase 36, by CT): acceptance run CRITERIA #96 (EC 247, Task 30775) failed in
# mh.asset.nrvv-criterion-check_1.0 after its work was written - print() of CC's criterion, which held '\u2264', to a
# Windows console in cp1252: "UnicodeEncodeError: 'charmap' codec can't encode character '\u2264'".
# Every Function's main() calls mh_task_io.load_params(argv) first.

import io as stdio
import sys

import pytest

import mh_task_io


def cp1252_console():
    return stdio.TextIOWrapper(stdio.BytesIO(), encoding='cp1252')


def test_after_load_params_the_console_prints_any_character_as_utf8(tmp_path, monkeypatch):
    params = tmp_path / 'params.yaml'
    params.write_text('task: {}\n', encoding='utf-8')
    console = cp1252_console()
    monkeypatch.setattr(sys, 'stdout', console)

    mh_task_io.load_params(['function.py', str(params)])

    print('criterion: the acknowledgement arrives in \u2264 60 seconds')
    console.flush()
    assert console.encoding.lower() == 'utf-8'
    assert 'arrives in \u2264 60'.encode('utf-8') in console.buffer.getvalue()
