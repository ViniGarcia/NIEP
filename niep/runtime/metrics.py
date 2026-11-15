"""Non-streaming runtime counters; percentages are computed by the application."""
import os


def vm_counters(vm):
    domain = vm.VIRT_VM
    if domain is None or not domain.isActive():
        return {'state': 'stopped', 'cpu_time_ns': 0, 'memory_bytes': 0, 'identity': None}
    info = domain.info()
    memory = domain.memoryStats()
    return {'state': 'running', 'identity': f'{domain.UUIDString()}:{domain.ID()}',
            'cpu_time_ns': info[4], 'memory_bytes': memory.get('rss', None) * 1024
            if memory.get('rss') is not None else None,
            'memory_limit_bytes': info[1] * 1024}


def container_counters(container):
    handle = container.CONTAINER
    if handle is None:
        return {'state': 'stopped', 'cpu_time_ns': 0, 'memory_bytes': 0, 'identity': None}
    handle.reload()
    if handle.status != 'running':
        return {'state': handle.status, 'cpu_time_ns': 0, 'memory_bytes': 0, 'identity': None}
    stats = handle.stats(stream=False, one_shot=True)
    memory = stats.get('memory_stats', {})
    return {'state': 'running',
            'identity': f'{handle.id}:{handle.attrs.get("State", {}).get("StartedAt", "")}',
            'cpu_time_ns': stats.get('cpu_stats', {}).get('cpu_usage', {}).get('total_usage'),
            'memory_bytes': memory.get('usage'), 'memory_limit_bytes': memory.get('limit')}


def daemon_counters():
    import psutil

    process = psutil.Process(os.getpid())
    cpu = process.cpu_times()
    return {'state': 'running', 'identity': f'{process.pid}:{process.create_time()}',
            'cpu_time_ns': int((cpu.user + cpu.system) * 1_000_000_000),
            'memory_bytes': process.memory_info().rss, 'pid': process.pid}
