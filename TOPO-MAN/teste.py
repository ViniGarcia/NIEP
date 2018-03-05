#!/usr/bin/python

from mininet.net import Mininet
from mininet.node import Controller
from mininet.cli import CLI
from mininet.link import Intf
from mininet.log import setLogLevel, info

def myNetwork():

    net = Mininet( topo=None,
                   build=False)

    info( '*** Adding controller\n' )
    net.addController(name='c0')

    info( '*** Add switches\n')
    s1 = net.addSwitch('s1')
    Intf( 'eth0', node=s1 )

    info( '*** Add hosts\n')
    h1 = net.addHost('h1', ip='10.0.0.157')

    info( '*** Add links\n')
    net.addLink(h1, s1)

    info( '*** Starting network\n')
    net.start()
    h1.cmdPrint('dhclient '+h1.defaultIntf().name)
    print h1.IP()
    CLI(net)
    net.stop()

if __name__ == '__main__':
    setLogLevel( 'info' )
    myNetwork()