"""HTTP readiness before Mininet: libvirt management or container loopback."""
import http.client
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


CONTAINER_PROBE = '''import http.client,sys,time
c=http.client.HTTPConnection("127.0.0.1",8080,timeout=float(sys.argv[1]))
try:
 c.request("GET","/health"); r=c.getresponse()
 if r.status==200 and r.read(3)==b"ok": print(time.perf_counter_ns())
finally: c.close()
'''


def vm_probe(domain):
    root = ET.fromstring(domain.XMLDesc(0))
    interface = root.find("devices/interface[@type='network']")
    if interface is None:
        raise ValueError('VM has no libvirt management network for HTTP probing')
    mac = interface.find('mac').get('address')
    network = domain.connect().networkLookupByName(interface.find('source').get('network'))

    def probe(timeout):
        leases = network.DHCPLeases(mac=mac)
        address = next((r['ipaddr'] for r in leases if r.get('mac', '').lower() == mac.lower()
                        and ':' not in r.get('ipaddr', '')), None)
        if not address:
            return None
        connection = http.client.HTTPConnection(address, 8080, timeout=timeout)
        try:
            connection.request('GET', '/health')
            response = connection.getresponse()
            if response.status == 200 and response.read(3) == b'ok':
                return time.perf_counter_ns()
        finally:
            connection.close()
        return None

    return probe


def container_probe(container):
    def probe(timeout):
        info = container.client.api.inspect_container(container.id)
        pid = info.get('State', {}).get('Pid', 0)
        if not isinstance(pid, int) or pid <= 0:
            return None
        result = subprocess.run(['nsenter', '-t', str(pid), '-n', sys.executable, '-c',
                                 CONTAINER_PROBE, str(timeout)], capture_output=True, text=True,
                                timeout=timeout + 1)
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip())
        if result.returncode:
            raise RuntimeError(result.stderr.strip()[-500:] or 'Container HTTP probe failed')
        return None

    return probe
