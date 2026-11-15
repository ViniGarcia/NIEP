"""Plot aggregation must preserve trial weighting and CSV joins."""
from pathlib import Path
import runpy
import statistics

import pytest


PLOT = runpy.run_path(str(Path(__file__).resolve().parents[3] / 'benchmarks/startup/plot.py'))


def startup(scenario, count=2, status='ready', run='r1'):
    return [dict(run_id=run, scenario_id=scenario, kind='vm', count=str(count), repeat='1',
                 instance=f'vm{i}', ready_ms=str(1000 * (i + 1)), status=status)
            for i in range(count)]


def usage(scenario, index, memory=1048576, cpu=10, count=2, run='r1'):
    return [dict(run_id=run, scenario_id=scenario, kind='vm', count=str(count), repeat='1',
                 instance=f'vm{i}', sample_index=str(index), memory_bytes=str(memory),
                 cpu_percent=str(cpu), status='sampled') for i in range(count)]


def test_startup_is_last_ready_and_resources_are_trial_averages():
    rows = startup('s1')
    samples = usage('s1', 1) + usage('s1', 2, memory=3 * 1048576, cpu=30)
    results, skipped = PLOT['aggregate'](rows, samples, {'r1'})
    assert skipped == 0
    assert results[0]['startup_seconds'] == 2
    assert results[0]['memory_mib'] == 4
    assert results[0]['cpu_percent'] == 40


def test_repetitions_are_equally_weighted_despite_different_poll_counts():
    rows = startup('s1') + startup('s2')
    samples = usage('s1', 1, cpu=10)
    samples += [r for i in range(10) for r in usage('s2', i, cpu=30)]
    results, _ = PLOT['aggregate'](rows, samples, {'r1'})
    points = PLOT['curve_points'](results, 'vm', 'cpu_percent')
    assert points[0][1:] == (40, statistics.stdev([20, 60]), 2)
    bars = PLOT['per_instance_points'](results, 'cpu_percent')
    assert bars[0][1:] == (20, statistics.stdev([10, 30]), 2)


def test_filters_failures_incomplete_polls_and_unrelated_runs():
    rows = startup('good') + startup('bad', status='timeout') + startup('other', run='r2')
    samples = usage('good', 1)[:1] + usage('bad', 1) + usage('other', 1, run='r2')
    results, skipped = PLOT['aggregate'](rows, samples, {'r1'})
    assert skipped == 1
    assert len(results) == 1
    assert results[0]['startup_seconds'] == 2
    assert results[0]['memory_mib'] is None


def test_instance_normalization_does_not_weight_larger_topologies_more():
    scenarios = [dict(kind='vm', count=1, memory_mib=100),
                 dict(kind='vm', count=64, memory_mib=12800)]
    points = PLOT['per_instance_points'](scenarios, 'memory_mib')
    assert points[0][1:] == (150, statistics.stdev([100, 200]), 2)


def test_csv_snapshot_ignores_an_incomplete_trailing_record(tmp_path):
    path = tmp_path / 'test.csv'
    path.write_text('run_id,status\nr1,ready\nr2,"unfinished')
    rows = PLOT['read_csv'](path, {'run_id', 'status'})
    assert rows == [dict(run_id='r1', status='ready')]


def test_numeric_metrics_reject_non_finite_values():
    with pytest.raises(ValueError, match='Invalid'):
        PLOT['number']({'cpu_percent': 'nan'}, 'cpu_percent')


def test_render_outputs_only_png_in_both_languages_without_sample_annotations(tmp_path, monkeypatch):
    pytest.importorskip('matplotlib')
    from matplotlib.figure import Figure

    captured = []

    def savefig(figure, path, **_kwargs):
        captured.append((path, figure.axes[0].get_title(),
                         [text.get_text() for ax in figure.axes for text in ax.texts]))

    monkeypatch.setattr(Figure, 'savefig', savefig)
    scenarios = [dict(kind=kind, count=2, startup_seconds=seconds, cpu_percent=cpu, memory_mib=memory)
                 for kind in ('vm', 'container')
                 for seconds, cpu, memory in [(1, 10, 50), (2, 20, 100)]]
    for language in ('pt', 'en'):
        PLOT['render'](scenarios, tmp_path / language, 'test', language)
    assert len(captured) == 10
    assert all(path.suffix == '.png' for path, _, _ in captured)
    assert {path.parent.name for path, _, _ in captured} == {'pt', 'en'}
    assert any(title == 'Tempo de inicialização da topologia' for _, title, _ in captured)
    assert any(title == 'Topology startup time' for _, title, _ in captured)
    assert all('n=' not in label for _, _, labels in captured for label in labels)
