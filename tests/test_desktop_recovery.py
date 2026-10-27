"""Exercise native recovery callbacks without starting Qt or an audio engine."""
import ast
from pathlib import Path
from types import SimpleNamespace


def callbacks():
    tree = ast.parse((Path(__file__).parents[1] / 'desktop.py').read_text(encoding='utf-8'))
    window = next(node for node in ast.walk(tree) if isinstance(node, ast.ClassDef) and node.name == 'AudioWindow')
    methods = [node for node in window.body if isinstance(node, ast.FunctionDef) and node.name in ('renderer_stopped', 'display_loaded', 'reload_display')]
    namespace = {'QUrl': lambda value: value}
    exec(compile(ast.Module(body=methods, type_ignores=[]), 'desktop recovery callbacks', 'exec'), namespace)
    return namespace


def test_renderer_failure_shows_native_recovery_and_logs_exit_only(capsys):
    messages = []
    window = SimpleNamespace(show_recovery=messages.append)
    callbacks()['renderer_stopped'](window, SimpleNamespace(name='CrashedTerminationStatus'), 7)
    assert len(messages) == 1 and 'stopped unexpectedly' in messages[0]
    assert capsys.readouterr().out == 'Display renderer stopped: CrashedTerminationStatus; exit code 7\n'


def test_failed_load_recovers_and_reload_only_navigates_display():
    messages, navigation, selected, status = [], [], [], []
    view = SimpleNamespace(url=lambda: SimpleNamespace(scheme=lambda: 'http'), load=navigation.append)
    window = SimpleNamespace(view=view, allow_close=False, show_recovery=messages.append,
                             stack=SimpleNamespace(setCurrentWidget=selected.append),
                             statusBar=lambda: SimpleNamespace(showMessage=status.append))
    methods = callbacks()
    methods['display_loaded'](window, False)
    assert len(messages) == 1
    methods['reload_display'](window)
    assert navigation == ['http://127.0.0.1:8765/'] and selected == [view]
    methods['display_loaded'](window, True)
    assert 'Local desktop app' in status[-1]
    window.allow_close = True
    methods['display_loaded'](window, False)
    assert len(messages) == 1
