import sys
import random
import networkx


def parseGraph(graphml_path):
    
    try:
        graph = networkx.read_graphml(graphml_path)
    except:
        print("ERROR: INAVLID GRAPHML PROVIDED!")
        exit()

    return graph


def writeGraph(graph, graphml_path):

    try:
       networkx.write_graphml(graph, graphml_path)
    except:
        print("ERROR: COULD NOT WRITE GRAPHML FILE!")
        exit()


def sfcGraph(service_linear_size):

    graph = networkx.Graph()
    graph.graph.update({"ID": "SFC#1"})
    
    graph.add_node("0")
    for sf in range(1, service_linear_size):
        graph.add_node(str(sf))
        graph.add_edge(str(sf-1), str(sf))

    return graph


def sffNodes(service_mapping):

    graph = networkx.Graph()

    maps = {}
    index = 0
    for key in service_mapping:

        if not service_mapping[key] in maps:
            graph.add_node("SFF#" + str(index))
            maps[service_mapping[key]] = "SFF#" + str(index)
            index += 1
        if "SFC#1" in graph.nodes[maps[service_mapping[key]]]:
            graph.nodes[maps[service_mapping[key]]]["SFC#1"] = graph.nodes[maps[service_mapping[key]]]["SFC#1"] + ";" + str(key)
        else:
            graph.nodes[maps[service_mapping[key]]]["SFC#1"] = str(key)
            

    return graph


def randomMapping(network_topology, service_linear_size):

    network_nodes = list(network_topology.nodes())

    for attempts in range(10):
        random_index = network_nodes.index(random.choice(network_nodes))
        random_mapping = {0:network_nodes[random_index]}

        for service_index in range(1, service_linear_size):
            nodes_radar = list(networkx.bfs_tree(network_topology, source=network_nodes[random_index], depth_limit=5).nodes())
            nodes_radar.remove(network_nodes[random_index])
            nodes_radar = [node for node in nodes_radar if not node in list(random_mapping.values())]
           
            if len(nodes_radar) == 0:
                break

            node_choice = random.choice(nodes_radar)
            random_mapping[service_index] = node_choice

        if len(random_mapping) == service_linear_size:
            return random_mapping

    return {}


if len(sys.argv) != 3:
    print("ERROR: INVALID ARGUMENTS! [*.py network_graphml service_linear_size]")
    exit()

network_topology = parseGraph(sys.argv[1])
try:
    service_linear_size = int(sys.argv[2])
except:
    print("ERROR: INVALID VALUE FOR service_linear_size!")
    exit()

service_mapping = randomMapping(network_topology, service_linear_size)
if len(service_mapping) == 0:
    print("ERROR: COULD NOT MAP THE SERVICE WITH RANDOM MAPPING!")
    exit()

for key in service_mapping:
   network_topology.nodes[service_mapping[key]]["SFC#1"] = str(key)
network_service = sfcGraph(service_linear_size)
minimum_forwarders = sffNodes(service_mapping)

writeGraph(network_service, sys.argv[1] + "SFC.graphml")
writeGraph(network_topology, sys.argv[1] + "MAPPED.graphml")
writeGraph(minimum_forwarders, sys.argv[1] + "SFF.graphml")