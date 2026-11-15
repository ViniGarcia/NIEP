#!/usr/bin/env python3
"""Plot startup and resource measurements from NIEP benchmark CSVs."""
import argparse
from collections import defaultdict
import csv
import io
import math
import os
from pathlib import Path
import statistics
import sys


KINDS = ('vm', 'container')
LABELS = {'vm': 'VM', 'container': 'Container'}
COLORS = {'vm': '#0072B2', 'container': '#D55E00'}


def read_csv(path, required):
    # Snapshot the current file length. Do not lock the running benchmark.
    with path.open('rb') as source:
        snapshot = source.read(os.fstat(source.fileno()).st_size).decode('utf-8')
    reader = csv.DictReader(io.StringIO(snapshot), strict=True)
    if not required.issubset(reader.fieldnames or ()):
        raise ValueError(f'{path}: missing columns {sorted(required - set(reader.fieldnames or ())) }')
    rows = []
    try:
        for row in reader:
            if None not in row and all(value is not None for value in row.values()):
                rows.append(row)
    except csv.Error:
        print(f'Ignoring an incomplete trailing CSV record in {path}', file=sys.stderr)
    return rows


def number(row, field):
    value = float(row[field])
    if not math.isfinite(value) or value < 0:
        raise ValueError(f'Invalid {field}: {row[field]!r}')
    return value


def host_memory_delta(records, scenario):
    """One host-wide delta per trial, with a complete pair of raw snapshots."""
    phases = {row['phase']: row for row in records}
    if (len(records) != 2 or set(phases) != {'before_topoup', 'before_topodown'}
            or any(row['status'] != 'sampled' or any(row[field] != scenario[field]
                                                   for field in ('kind', 'count', 'repeat'))
                   for row in records)):
        return None
    before, after = phases['before_topoup'], phases['before_topodown']
    fields = ('mem_total_bytes', 'mem_available_bytes')
    if any(row.get(field) in ('', None) for row in records for field in fields):
        return None
    totals = [number(row, 'mem_total_bytes') for row in (before, after)]
    available = [number(row, 'mem_available_bytes') for row in (before, after)]
    if any(total <= 0 or free > total for total, free in zip(totals, available)):
        raise ValueError('Invalid host memory counters')
    if totals[0] != totals[1]:
        return None  # RAM capacity changed; this pair is not comparable.
    # Used estimate = MemTotal - MemAvailable. Preserve negative deltas.
    return (available[0] - available[1]) / 1048576


def disk_total(records, scenario, instances):
    expected_source = {'vm': 'host_allocated_blocks', 'container': 'docker_writable_layer'}[scenario['kind']]
    if (len(records) != len(instances) or {r['instance'] for r in records} != instances
            or any(r['status'] != 'sampled' or r.get('source') != expected_source
                   or any(r[field] != scenario[field] for field in ('kind', 'count', 'repeat'))
                   or r.get('disk_bytes') in ('', None) for r in records)):
        return None
    return sum(number(row, 'disk_bytes') for row in records) / 1048576


def aggregate(startup, usage, run_ids, runtime=(), host_memory=(), disk_usage=()):
    """One observation per complete scenario/repetition, never per polling row."""
    scenarios = defaultdict(list)
    for row in startup:
        if row['run_id'] in run_ids:
            scenarios[(row['run_id'], row['scenario_id'])].append(row)
    polls = defaultdict(lambda: defaultdict(list))
    for row in usage:
        key = (row['run_id'], row['scenario_id'])
        if key in scenarios:
            polls[key][row['sample_index']].append(row)
    runtime_groups = defaultdict(list)
    for row in runtime:
        runtime_groups[(row['run_id'], row['scenario_id'])].append(row)
    host_groups = defaultdict(list)
    for row in host_memory:
        host_groups[(row['run_id'], row['scenario_id'])].append(row)
    disk_groups = defaultdict(list)
    for row in disk_usage:
        disk_groups[(row['run_id'], row['scenario_id'])].append(row)
    results, skipped = [], 0
    for key, rows in scenarios.items():
        first = rows[0]
        count = int(first['count'])
        kind = first['kind']
        instances = {row['instance'] for row in rows}
        if (kind not in KINDS or count < 1 or len(rows) != count or len(instances) != count
                or any(row['status'] != 'ready' or row['kind'] != kind
                       or row['count'] != first['count'] or row['repeat'] != first['repeat'] for row in rows)):
            skipped += 1
            continue
        result = dict(run_id=key[0], scenario_id=key[1], kind=kind, count=count,
                      startup_seconds=max(number(row, 'ready_ms') for row in rows) / 1000,
                      memory_mib=None, cpu_percent=None, topoup_seconds=None,
                      host_memory_delta_mib=host_memory_delta(host_groups[key], first),
                      disk_mib=disk_total(disk_groups[key], first, instances),
                      runtime_start_call_ms=None, runtime_http_ready_ms=None)
        topoup_values = {number(row, 'topoup_ms') for row in rows if row.get('topoup_ms') not in ('', None)}
        if len(topoup_values) > 1:
            raise ValueError(f'Inconsistent topoup_ms in scenario {key}')
        if topoup_values:
            result['topoup_seconds'] = topoup_values.pop() / 1000
        timings = runtime_groups[key]
        if (len(timings) == count and {r['instance'] for r in timings} == instances
                and all(r['status'] == 'ready' and r['kind'] == kind and r['count'] == first['count']
                        and r['repeat'] == first['repeat'] for r in timings)):
            for field, metric in (('start_call_ms', 'runtime_start_call_ms'),
                                  ('runtime_ready_ms', 'runtime_http_ready_ms')):
                if all(r.get(field) not in ('', None) for r in timings):
                    result[metric] = statistics.fmean(number(r, field) for r in timings)
        memory_totals, cpu_totals = [], []
        for samples in polls[key].values():
            if (len(samples) != count or {r['instance'] for r in samples} != instances
                    or any(r['status'] != 'sampled' or r['kind'] != kind
                           or r['count'] != first['count'] or r['repeat'] != first['repeat']
                           for r in samples)):
                continue
            if all(r['memory_bytes'] != '' for r in samples):
                memory_totals.append(sum(number(r, 'memory_bytes') for r in samples))
            if all(r['cpu_percent'] != '' for r in samples):
                cpu_totals.append(sum(number(r, 'cpu_percent') for r in samples))
        if memory_totals:
            result['memory_mib'] = statistics.fmean(memory_totals) / 1048576
        if cpu_totals:
            result['cpu_percent'] = statistics.fmean(cpu_totals)
        results.append(result)
    return results, skipped


def mean_sd(values):
    return statistics.fmean(values), statistics.stdev(values) if len(values) > 1 else 0.0


def curve_points(scenarios, kind, metric):
    groups = defaultdict(list)
    for row in scenarios:
        if row['kind'] == kind and row.get(metric) is not None:
            groups[row['count']].append(row[metric])
    return [(count, *mean_sd(values), len(values)) for count, values in sorted(groups.items())]


def per_instance_points(scenarios, metric):
    # Each scenario/repetition contributes one normalized observation, regardless
    # of its entity count or number of polling snapshots.
    groups = defaultdict(list)
    for row in scenarios:
        if row.get(metric) is not None:
            groups[row['kind']].append(row[metric] / row['count'])
    return [(kind, *mean_sd(groups[kind]), len(groups[kind])) for kind in KINDS if groups[kind]]


def render(scenarios, output, selection, language='en'):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False})
    portuguese = language == 'pt'
    labels = {'vm': 'VM', 'container': 'Contêiner'} if portuguese else LABELS
    footer = ('Barras de erro: ±1 desvio padrão; indisponível com uma única repetição.'
              if portuguese else
              'Error bars: ±1 sample SD; unavailable with a single trial.')
    no_data = 'Sem observações completas' if portuguese else 'No complete observations'
    xlabel = 'Número de instâncias' if portuguese else 'Number of instances'
    curve_labels = {
        'topoup_seconds': ('Duração do topoup por cenário', 'Duração do comando topoup (s)'),
        'startup_seconds': ('Tempo de inicialização da topologia', 'Tempo até todas as instâncias responderem HTTP (s)'),
        'cpu_percent': ('Uso médio de CPU do cenário', 'Uso agregado de CPU (%) — 100% por núcleo'),
        'memory_mib': ('Uso médio de memória do cenário', 'Uso agregado de memória (MiB)'),
        'host_memory_delta_mib': ('Variação estimada de memória usada do host', 'Delta de memória usada do host (MiB)'),
        'disk_mib': ('Uso de disco privado ao final do cenário', 'Disco privado agregado (MiB)'),
        'runtime_start_call_ms': ('Duração média da chamada de start por instância', 'Duração da chamada ao runtime (ms)'),
        'runtime_http_ready_ms': ('Tempo médio de start até HTTP por instância', 'Tempo do start do runtime até HTTP pronto (ms)'),
    }
    bar_labels = {
        'memory_mib': ('Uso de memória por instância entre cenários', 'Memória média por instância (MiB)'),
        'cpu_percent': ('Uso de CPU por instância entre cenários', 'CPU média por instância (%) — 100% por núcleo'),
    }

    def save(fig, name):
        caption = footer
        if name == 'disk_usage':
            caption = ('VM: blocos alocados; contêiner: camada gravável. Exclui imagens compartilhadas, volumes e logs do runtime.'
                       if portuguese else
                       'VM: allocated blocks; container: writable layer. Excludes shared images, volumes and runtime logs.') + '\n' + footer
        fig.text(.5, .015, caption, ha='center', fontsize=8)
        fig.tight_layout(rect=(0, .085 if name == 'disk_usage' else .055, 1, 1))
        fig.savefig(output / f'{name}.png', dpi=180, bbox_inches='tight')
        plt.close(fig)

    for metric, name, title, ylabel in (
        ('topoup_seconds', 'topoup_time', 'topoup duration per scenario', 'topoup command duration (s)'),
        ('startup_seconds', 'startup_time', 'Topology startup time', 'Time until all instances respond to HTTP (s)'),
        ('cpu_percent', 'cpu_mean', 'Mean scenario CPU usage', 'Aggregate CPU usage (%) — 100% per core'),
        ('memory_mib', 'memory_mean', 'Mean scenario memory usage', 'Aggregate memory usage (MiB)'),
        ('host_memory_delta_mib', 'host_memory_delta', 'Estimated host used-memory change', 'Host used-memory delta (MiB)'),
        ('disk_mib', 'disk_usage', 'Private disk usage at scenario end', 'Aggregate private disk usage (MiB)'),
        ('runtime_start_call_ms', 'runtime_start_call', 'Mean start API duration per instance', 'Runtime start API duration (ms)'),
        ('runtime_http_ready_ms', 'runtime_http_ready', 'Mean runtime start-to-HTTP time per instance', 'Runtime start to HTTP readiness (ms)'),
    ):
        if portuguese:
            title, ylabel = curve_labels[metric]
        fig, ax = plt.subplots(figsize=(8, 5))
        counts = set()
        plotted = False
        for kind, marker in zip(KINDS, ('o', 's')):
            points = curve_points(scenarios, kind, metric)
            if not points:
                continue
            plotted = True
            x, means, deviations, ns = zip(*points)
            counts.update(x)
            errors = None if all(n == 1 for n in ns) else [sd if n > 1 else math.nan for sd, n in zip(deviations, ns)]
            ax.errorbar(x, means, yerr=errors, label=labels[kind], color=COLORS[kind],
                        marker=marker, capsize=4, linewidth=1.7)
        if counts:
            ax.set_xscale('log', base=2)
            ax.set_xticks(sorted(counts), labels=[str(n) for n in sorted(counts)])
        if plotted:
            ax.legend()
        else:
            ax.text(.5, .5, no_data, transform=ax.transAxes, ha='center')
        ax.set(title=title, xlabel=xlabel, ylabel=ylabel)
        if metric == 'host_memory_delta_mib':
            ax.axhline(0, color='gray', linewidth=.8, linestyle='--')
        ax.grid(alpha=.25)
        save(fig, name)

    for metric, name, title, ylabel in (
        ('memory_mib', 'memory_per_instance', 'Memory usage per instance across scenario sizes', 'Mean memory per instance (MiB)'),
        ('cpu_percent', 'cpu_per_instance', 'CPU usage per instance across scenario sizes', 'Mean CPU per instance (%) — 100% per core'),
    ):
        if portuguese:
            title, ylabel = bar_labels[metric]
        fig, ax = plt.subplots(figsize=(7, 5))
        points = per_instance_points(scenarios, metric)
        for i, (kind, mean, deviation, n) in enumerate(points):
            ax.bar(i, mean, yerr=deviation if n > 1 else None, capsize=6, color=COLORS[kind], width=.55)
            ax.annotate(f'{mean:.2f}', (i, mean + deviation), xytext=(0, 7),
                        textcoords='offset points', ha='center', fontsize=10)
        ax.set_xticks(range(len(points)), labels=[labels[p[0]] for p in points])
        if not points:
            ax.text(.5, .5, no_data, transform=ax.transAxes, ha='center')
        ax.set(title=title, ylabel=ylabel)
        ax.grid(axis='y', alpha=.25)
        ax.set_axisbelow(True)
        ax.margins(y=.3)
        save(fig, name)
    print(f'Plots: {output} (PNG, {language}); runs: {selection}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path('benchmarks/startup/output'))
    parser.add_argument('--output', type=Path, help='Defaults to INPUT/plots')
    parser.add_argument('--run-id', nargs='+', default=['latest'],
                        help='Run IDs to include, or latest (default), or all')
    args = parser.parse_args()
    common = {'run_id', 'scenario_id', 'kind', 'count', 'repeat', 'instance', 'status'}
    startup = read_csv(args.input / 'startup.csv', common | {'ready_ms'})
    usage = read_csv(args.input / 'usage.csv', common | {'sample_index', 'memory_bytes', 'cpu_percent'})
    available = list(dict.fromkeys(row['run_id'] for row in startup))
    if not available:
        raise ValueError('No completed startup records yet; rerun after a scenario finishes')
    if args.run_id == ['latest']:
        selected = [available[-1]]
    elif args.run_id == ['all']:
        selected = available
    else:
        selected = args.run_id
        missing = set(selected) - set(available)
        if missing:
            raise ValueError(f'Unknown run IDs: {sorted(missing)}')
    runtime_path = args.input / 'runtime_startup.csv'
    runtime = read_csv(runtime_path, common | {'start_call_ms', 'runtime_ready_ms'}) if runtime_path.exists() else []
    host_path = args.input / 'host_memory.csv'
    host_required = (common - {'instance'}) | {'phase', 'mem_total_bytes', 'mem_available_bytes'}
    host_memory = read_csv(host_path, host_required) if host_path.exists() else []
    disk_path = args.input / 'disk_usage.csv'
    disk_usage = read_csv(disk_path, common | {'disk_bytes', 'source'}) if disk_path.exists() else []
    scenarios, skipped = aggregate(startup, usage, set(selected), runtime, host_memory, disk_usage)
    if not scenarios:
        raise ValueError('No successful, complete scenarios in the selected runs')
    print(f'Selected runs: {", ".join(selected)}; complete scenarios: {len(scenarios)}; skipped: {skipped}')
    captured = sum(row['runtime_http_ready_ms'] is not None for row in scenarios)
    print(f'In-topology runtime timing scenarios: {captured}/{len(scenarios)}')
    captured_host = sum(row['host_memory_delta_mib'] is not None for row in scenarios)
    print(f'Host memory delta scenarios: {captured_host}/{len(scenarios)}')
    captured_disk = sum(row['disk_mib'] is not None for row in scenarios)
    print(f'Disk usage scenarios: {captured_disk}/{len(scenarios)}')
    for kind in KINDS:
        for count, mean, sd, n in curve_points(scenarios, kind, 'startup_seconds'):
            deviation = f'{sd:.3f}s' if n > 1 else 'n/a (one trial)'
            print(f'{kind} n={count}: startup={mean:.3f}s, SD={deviation}, trials={n}')
    for language in ('pt', 'en'):
        render(scenarios, (args.output or args.input / 'plots') / language, ', '.join(selected), language)


if __name__ == '__main__':
    try:
        main()
    except ImportError as exc:
        raise SystemExit('Install plotting dependencies: pip install -e ".[benchmark]"') from exc
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
