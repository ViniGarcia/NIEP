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


def aggregate(startup, usage, run_ids):
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
                      memory_mib=None, cpu_percent=None)
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
        if row['kind'] == kind and row[metric] is not None:
            groups[row['count']].append(row[metric])
    return [(count, *mean_sd(values), len(values)) for count, values in sorted(groups.items())]


def per_instance_points(scenarios, metric):
    # Each scenario/repetition contributes one normalized observation, regardless
    # of its entity count or number of polling snapshots.
    groups = defaultdict(list)
    for row in scenarios:
        if row[metric] is not None:
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
        'startup_seconds': ('Tempo de inicialização da topologia', 'Tempo até todas as instâncias responderem HTTP (s)'),
        'cpu_percent': ('Uso médio de CPU do cenário', 'Uso agregado de CPU (%) — 100% por núcleo'),
        'memory_mib': ('Uso médio de memória do cenário', 'Uso agregado de memória (MiB)'),
    }
    bar_labels = {
        'memory_mib': ('Uso de memória por instância entre cenários', 'Memória média por instância (MiB)'),
        'cpu_percent': ('Uso de CPU por instância entre cenários', 'CPU média por instância (%) — 100% por núcleo'),
    }

    def save(fig, name):
        fig.text(.5, .015, footer, ha='center', fontsize=8)
        fig.tight_layout(rect=(0, .055, 1, 1))
        fig.savefig(output / f'{name}.png', dpi=180, bbox_inches='tight')
        plt.close(fig)

    for metric, name, title, ylabel in (
        ('startup_seconds', 'startup_time', 'Topology startup time', 'Time until all instances respond to HTTP (s)'),
        ('cpu_percent', 'cpu_mean', 'Mean scenario CPU usage', 'Aggregate CPU usage (%) — 100% per core'),
        ('memory_mib', 'memory_mean', 'Mean scenario memory usage', 'Aggregate memory usage (MiB)'),
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
    scenarios, skipped = aggregate(startup, usage, set(selected))
    if not scenarios:
        raise ValueError('No successful, complete scenarios in the selected runs')
    print(f'Selected runs: {", ".join(selected)}; complete scenarios: {len(scenarios)}; skipped: {skipped}')
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
