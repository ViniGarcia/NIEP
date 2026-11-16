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
    scenarios = [dict(kind=kind, count=2, startup_seconds=seconds, topoup_seconds=seconds / 2, cpu_percent=cpu, memory_mib=memory,
                      host_memory_delta_mib=memory - 75,
                      disk_mib=memory,
                      disk_total_mib=memory + 10,
                      runtime_start_call_ms=cpu * 10, runtime_http_ready_ms=seconds * 1000)
                 for kind in ('vm', 'container')
                 for seconds, cpu, memory in [(1, 10, 50), (2, 20, 100)]]
    for language in ('pt', 'en'):
        PLOT['render'](scenarios, tmp_path / language, 'test', language)
    assert len(captured) == 22
    assert all(path.suffix == '.png' for path, _, _ in captured)
    assert {path.parent.name for path, _, _ in captured} == {'pt', 'en'}
    assert any(title == 'Tempo de inicialização da topologia' for _, title, _ in captured)
    assert any(title == 'Topology startup time' for _, title, _ in captured)
    assert all('n=' not in label for _, _, labels in captured for label in labels)
    assert {path.stem for path, _, _ in captured} >= {'runtime_start_call', 'runtime_http_ready'}
    assert any(title == 'Duração média da chamada de start por instância' for _, title, _ in captured)
    assert {path.stem for path, _, _ in captured} >= {'host_memory_delta'}
    assert any(title == 'Variação estimada de memória usada do host' for _, title, _ in captured)
    assert {path.stem for path, _, _ in captured} >= {'disk_usage'}
    assert any(title == 'Uso de disco privado ao final do cenário' for _, title, _ in captured)


def runtime(scenario, calls=(100, 300), readiness=(1000, 3000)):
    return [dict(run_id='r1', scenario_id=scenario, kind='vm', count='2', repeat='1',
                 instance=f'vm{i}', start_call_ms=str(call), runtime_ready_ms=str(ready),
                 status='ready')
            for i, (call, ready) in enumerate(zip(calls, readiness))]


def test_runtime_metrics_join_instances_and_average_per_trial_before_sd():
    starts = startup('s1') + startup('s2')
    timings = runtime('s1') + runtime('s2', calls=(500, 700), readiness=(5000, 7000))
    results, _ = PLOT['aggregate'](starts, [], {'r1'}, timings)
    assert [r['runtime_start_call_ms'] for r in results] == [200, 600]
    assert [r['runtime_http_ready_ms'] for r in results] == [2000, 6000]
    points = PLOT['curve_points'](results, 'vm', 'runtime_start_call_ms')
    assert points == [(2, 400, statistics.stdev([200, 600]), 2)]


def test_incomplete_or_unmatched_runtime_records_are_not_filled_with_zero():
    starts = startup('s1')
    for timings in (runtime('s1')[:1], runtime('other'), runtime('s1') + runtime('s1')):
        results, _ = PLOT['aggregate'](starts, [], {'r1'}, timings)
        assert results[0]['startup_seconds'] == 2
        assert results[0]['runtime_start_call_ms'] is None
        assert results[0]['runtime_http_ready_ms'] is None


def test_topoup_counts_one_observation_per_scenario_repetition():
    rows = [dict(row, topoup_ms='1000') for row in startup('s1')]
    rows += [dict(row, topoup_ms='3000') for row in startup('s2')]
    scenarios, _ = PLOT['aggregate'](rows, [], {'r1'})
    assert [r['topoup_seconds'] for r in scenarios] == [1, 3]
    assert PLOT['curve_points'](scenarios, 'vm', 'topoup_seconds') == [
        (2, 2, statistics.stdev([1, 3]), 2)]


def test_topoup_rejects_inconsistent_copies_within_a_scenario():
    rows = startup('s1')
    rows[0]['topoup_ms'], rows[1]['topoup_ms'] = '1000', '2000'
    with pytest.raises(ValueError, match='Inconsistent topoup_ms'):
        PLOT['aggregate'](rows, [], {'r1'})
    assert PLOT['aggregate'](startup('s1'), [], {'r1'})[0][0]['topoup_seconds'] is None


def host_memory(scenario, before=800, after=700, total=1024, run='r1'):
    return [dict(run_id=run, scenario_id=scenario, kind='vm', count='2', repeat='1',
                 phase=phase, mem_total_bytes=str(total * 1048576),
                 mem_available_bytes=str(available * 1048576), status='sampled')
            for phase, available in [('before_topoup', before), ('before_topodown', after)]]


def test_host_delta_joins_by_run_and_scenario_and_counts_each_trial_once():
    starts = startup('s1') + startup('s2')
    snapshots = host_memory('s1') + host_memory('s2', before=800, after=900)
    snapshots += host_memory('s1', run='other', before=1000, after=0)
    results, _ = PLOT['aggregate'](starts, [], {'r1'}, host_memory=snapshots)
    assert [r['host_memory_delta_mib'] for r in results] == [100, -100]
    assert PLOT['curve_points'](results, 'vm', 'host_memory_delta_mib') == [
        (2, 0, statistics.stdev([100, -100]), 2)]
    assert all(r['memory_mib'] is None for r in results)  # Independent of per-instance samples.


def test_absent_incomplete_invalid_or_unmatched_host_pairs_are_not_zero():
    complete = host_memory('s1')
    cases = [[], complete[:1], complete + complete, host_memory('other'),
             [complete[0], dict(complete[1], status='metrics_error')],
             [complete[0], dict(complete[1], mem_available_bytes='')],
             [complete[0], dict(complete[1], kind='container')],
             [complete[0], dict(complete[1], count='64')],
             [complete[0], dict(complete[1], repeat='2')],
             [complete[0], dict(complete[1], mem_total_bytes=str(2048 * 1048576))]]
    for snapshots in cases:
        results, _ = PLOT['aggregate'](startup('s1'), [], {'r1'}, host_memory=snapshots)
        assert results[0]['host_memory_delta_mib'] is None
        assert results[0]['startup_seconds'] == 2


def test_host_memory_zero_delta_is_a_valid_observation():
    results, _ = PLOT['aggregate'](startup('s1'), [], {'r1'},
                                   host_memory=host_memory('s1', before=800, after=800))
    assert PLOT['curve_points'](results, 'vm', 'host_memory_delta_mib') == [(2, 0, 0, 1)]


@pytest.mark.parametrize('field,value', [('mem_total_bytes', 'nan'),
                                       ('mem_available_bytes', '-1'),
                                       ('mem_available_bytes', str(2048 * 1048576))])
def test_host_delta_rejects_invalid_raw_counters(field, value):
    snapshots = host_memory('s1')
    snapshots[0][field] = value
    with pytest.raises(ValueError, match='Invalid'):
        PLOT['aggregate'](startup('s1'), [], {'r1'}, host_memory=snapshots)


def disk(scenario, sizes=(1048576, 3 * 1048576), run='r1', kind='vm'):
    return [dict(run_id=run, scenario_id=scenario, kind=kind, count='2', repeat='1',
                 instance=f'vm{i}', disk_bytes=str(size), status='sampled',
                 source='host_allocated_blocks' if kind == 'vm' else 'docker_writable_layer')
            for i, size in enumerate(sizes)]


def test_disk_sums_instances_once_per_trial_and_joins_exact_scenario():
    starts = startup('s1') + startup('s2')
    records = disk('s1') + disk('s2', sizes=(4 * 1048576, 4 * 1048576))
    records += disk('s1', sizes=(999999999, 999999999), run='unrelated')
    results, _ = PLOT['aggregate'](starts, [], {'r1'}, disk_usage=records)
    assert [r['disk_mib'] for r in results] == [4, 8]
    assert PLOT['curve_points'](results, 'vm', 'disk_mib') == [(2, 6, statistics.stdev([4, 8]), 2)]


def test_missing_or_invalid_disk_samples_do_not_become_zero_or_hide_startup():
    complete = disk('s1')
    for records in ([], complete[:1], complete + complete, disk('other'),
                    [complete[0], dict(complete[1], status='metrics_error')],
                    [complete[0], dict(complete[1], disk_bytes='')],
                    [complete[0], dict(complete[1], source='docker_writable_layer')],
                    [complete[0], dict(complete[1], instance='unmatched')],
                    [complete[0], dict(complete[1], count='64')],
                    [complete[0], dict(complete[1], repeat='2')]):
        results, _ = PLOT['aggregate'](startup('s1'), [], {'r1'}, disk_usage=records)
        assert results[0]['disk_mib'] is None
        assert results[0]['startup_seconds'] == 2


def test_zero_container_writable_layer_is_valid_disk_usage():
    starts = [dict(row, kind='container') for row in startup('s1')]
    results, _ = PLOT['aggregate'](starts, [], {'r1'},
                                   disk_usage=disk('s1', sizes=(0, 0), kind='container'))
    assert PLOT['curve_points'](results, 'container', 'disk_mib') == [(2, 0, 0, 1)]


def test_container_allocated_blocks_are_accepted_by_disk_plot():
    starts = [dict(row, kind='container') for row in startup('s1')]
    records = [dict(row, source='host_allocated_blocks')
               for row in disk('s1', kind='container')]
    results, _ = PLOT['aggregate'](starts, [], {'r1'}, disk_usage=records)
    assert PLOT['curve_points'](results, 'container', 'disk_mib') == [(2, 4, 0, 1)]


@pytest.mark.parametrize('image_ids,expected', [(['same', 'same'], 14), (['one', 'two'], 24)])
def test_disk_plot_adds_each_container_image_once(image_ids, expected):
    starts = [dict(row, kind='container') for row in startup('s1')]
    records = [dict(row, image_id=image_id, image_bytes=str(10 * 1048576),
                    image_source='docker_image_size')
               for row, image_id in zip(disk('s1', kind='container'), image_ids)]
    results, _ = PLOT['aggregate'](starts, [], {'r1'}, disk_usage=records)
    assert results[0]['disk_mib'] == 4
    assert results[0]['disk_total_mib'] == expected


def test_vm_disk_plot_never_adds_base_again():
    records = [dict(row, image_id='vm-base', image_bytes=str(100 * 1048576))
               for row in disk('s1')]
    results, _ = PLOT['aggregate'](startup('s1'), [], {'r1'}, disk_usage=records)
    assert results[0]['disk_total_mib'] == results[0]['disk_mib'] == 4


@pytest.mark.parametrize('change', [
    {'image_bytes': ''}, {'image_id': ''}, {'image_source': 'unknown'},
    {'image_error': 'unavailable'}, {'image_bytes': str(11 * 1048576)},
])
def test_missing_or_inconsistent_images_preserve_private_plot_only(change):
    starts = [dict(row, kind='container') for row in startup('s1')]
    records = [dict(row, image_id='same', image_bytes=str(10 * 1048576),
                    image_source='docker_image_size') for row in disk('s1', kind='container')]
    records[1].update(change)
    results, _ = PLOT['aggregate'](starts, [], {'r1'}, disk_usage=records)
    assert results[0]['disk_total_mib'] is None
    assert results[0]['disk_mib'] == 4


def test_historical_container_disk_without_images_is_not_presented_as_total():
    starts = [dict(row, kind='container') for row in startup('s1')]
    results, _ = PLOT['aggregate'](starts, [], {'r1'}, disk_usage=disk('s1', kind='container'))
    assert results[0]['disk_mib'] == 4
    assert results[0]['disk_total_mib'] is None


@pytest.mark.parametrize('container_size,scale', [(12, 'log'), (0, 'symlog')])
def test_disk_render_keeps_small_values_and_genuine_zero_visible(tmp_path, monkeypatch,
                                                               container_size, scale):
    pytest.importorskip('matplotlib')
    from matplotlib.figure import Figure

    captured = {}

    def savefig(figure, path, **_kwargs):
        if path.stem.startswith('disk_usage'):
            ax = figure.axes[0]
            captured[path.stem] = (ax.get_yscale(), [text.get_text() for text in ax.texts],
                                   ax.get_ylim())

    monkeypatch.setattr(Figure, 'savefig', savefig)
    scenarios = [dict(kind=kind, count=32, disk_mib=size, disk_total_mib=size)
                 for kind, size in [('vm', 4269), ('container', container_size)]]
    PLOT['render'](scenarios, tmp_path, 'test')
    assert set(captured) == {'disk_usage', 'disk_usage_private'}
    for actual_scale, annotations, limits in captured.values():
        assert actual_scale == scale
        assert f'{container_size:.2f} MiB' in annotations
        assert limits[0] <= container_size < limits[1]


@pytest.mark.parametrize('size', ['-1', 'nan', 'inf'])
def test_plot_rejects_invalid_disk_size(size):
    records = disk('s1')
    records[0]['disk_bytes'] = size
    with pytest.raises(ValueError, match='Invalid disk_bytes'):
        PLOT['aggregate'](startup('s1'), [], {'r1'}, disk_usage=records)
