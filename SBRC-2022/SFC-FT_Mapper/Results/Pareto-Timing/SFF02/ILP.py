import sys
import time
import copy
import numpy
import networkx
import itertools
import statistics


def parseGraph(graphml_path):
	
	try:
		graph = networkx.read_graphml(graphml_path)
	except:
		print("ERROR: INAVLID GRAPHML PROVIDED!")
		exit()

	return graph


def checkPremises(network_topology, service_topology, forwarders_topology, classifiers_n):

	if classifiers_n < 1:
		print("ERROR: INVALID VALUE OF classifiers_n PROVIDED!")
		exit()


	def sffEssentials(network_topology, service_topology, forwarders_topology):

		mapped_nodes_sf = {}
		mapping_nodes_sff = {}
		relation_sf_sff = {}
		basic_sff_mapping = {}

		sfc_id = service_topology.graph["ID"]
		for net_node in network_topology:
			if sfc_id in network_topology.nodes[net_node]:
				mapped_nodes_sf[net_node] = network_topology.nodes[net_node][sfc_id].split(";")

		for sff_node in forwarders_topology:
			if sfc_id in forwarders_topology.nodes[sff_node]:
				mapping_nodes_sff[sff_node] = forwarders_topology.nodes[sff_node][sfc_id].split(";")
				for sf in mapping_nodes_sff[sff_node]:
					if sf in relation_sf_sff:
						relation_sf_sff[sf] += 1
					else:
						relation_sf_sff[sf] = 1
			else:
				print("ERROR: THERE IS A SFF WITH NO ROUTES TO THE SFC (" +  str(sff) + ")")
				exit()

		if any(relation_sf_sff[sf] < 2 for sf in relation_sf_sff):
			print("ERROR: THERE EXIST A SF MAPPED TO A SINGLE SFF!")
			exit()

		for net_node in mapped_nodes_sf:
			for sff_node in mapping_nodes_sff:

				if all(sf in mapped_nodes_sf[net_node] for sf in mapping_nodes_sff[sff_node]):
					if not net_node in basic_sff_mapping:
						basic_sff_mapping[net_node] = sff_node

			if not net_node in basic_sff_mapping:
				print("ERROR: A BASIC SFF MAPPING COULD NOT BE DONE (" + str(net_node) + ")!")
				exit()

		return mapped_nodes_sf, mapping_nodes_sff, relation_sf_sff, basic_sff_mapping


	return sffEssentials(network_topology, service_topology, forwarders_topology)


def basicMapping(network_topology, basic_sff_mapping):
	
	mapped_sffs = []
	for net_node in basic_sff_mapping:
		if "SFF" in network_topology.nodes[net_node]:
			print("ERROR: MULTIPLE SFF ALLOCATED IN THE SAME NETWORK NODE (" + str(net_node) + ")!")
			exit()
		network_topology.nodes[net_node]["SFF"] = str(basic_sff_mapping[net_node])


def sffEvaluate(network_topology, mapping_nodes_component, component_neighboors, reversed_mapped_nodes_sf, component_mapping, cut_off):

	self_degree_sum = 0
	paths_degree_sum = 0

	component_keys = list(mapping_nodes_component.keys())
	for component_index in range(len(component_keys)):
		self_degree_sum += network_topology.degree[component_mapping[component_index]]

		for target_node in mapping_nodes_component[component_keys[component_index]]:
			for subgraph in networkx.all_simple_paths(network_topology, component_mapping[component_index], target_node, cutoff=cut_off):
				tmp_paths_degree_sum = 0
				for node in subgraph:
					tmp_paths_degree_sum += network_topology.degree[node]
				paths_degree_sum += tmp_paths_degree_sum / len(subgraph)

		if component_keys[component_index] in component_neighboors:
			for target_node in component_neighboors[component_keys[component_index]]:
				for subgraph in networkx.all_simple_paths(network_topology, component_mapping[component_index], target_node, cutoff=cut_off):
					tmp_paths_degree_sum = 0
					for node in subgraph:
						tmp_paths_degree_sum += network_topology.degree[node]
					paths_degree_sum += tmp_paths_degree_sum / len(subgraph)

	return (self_degree_sum, paths_degree_sum)


def sffCandidate(network_topology, reversed_mapped_nodes_sf, net_node, sff_inst):

	if "SFF" in network_topology.nodes[net_node]:
		return False

	for sf_inst in sff_inst:
		if not networkx.has_path(network_topology, net_node, reversed_mapped_nodes_sf[sf_inst]):
			return False

	return True


def sffRelations(service_topology, mapping_nodes_sff, reversed_mapped_nodes_sf, reversed_mapping_nodes_sff):

	sff_check_neighborhood = {}
	for sff_node in mapping_nodes_sff:
		sff_check_neighborhood[sff_node] = []
		for sf_node in mapping_nodes_sff[sff_node]:
			for sf_neigh in service_topology.neighbors(sf_node):
				if not sf_neigh in mapping_nodes_sff[sff_node]:
					sff_check_neighborhood[sff_node] += reversed_mapping_nodes_sff[sf_neigh]

	return sff_check_neighborhood


def sffNeighborhood(network_topology, mapping_nodes_sff, sff_neighborhood, sff_mapping):

	sff_neighbors = {}

	sff_keys = list(mapping_nodes_sff.keys())
	for sff_index in range(len(sff_keys)):
		if sff_keys[sff_index] in sff_neighborhood:
			sff_neighbors[sff_keys[sff_index]] = []
			for mapping_key in sff_neighborhood[sff_keys[sff_index]]:
				if not networkx.has_path(network_topology, sff_mapping[sff_index], sff_mapping[sff_keys.index(mapping_key)]):
					(False,)
				sff_neighbors[sff_keys[sff_index]].append(sff_mapping[sff_keys.index(mapping_key)])

	return (True, sff_neighbors)


def sffScoring(evaluation_results, weigh_metrics):

	scoring_results = [0] * len(evaluation_results[-1])
	for metric_index in range(len(weigh_metrics)):
		parameter = max(evaluation_results[metric_index])

		for result_index in range(len(evaluation_results[-1])):
			scoring_results[result_index] += evaluation_results[metric_index][result_index] / parameter * weigh_metrics[metric_index]

	return scoring_results


def paretoEfficient2(costs):

	is_efficient = numpy.arange(costs.shape[0])
	n_points = costs.shape[0]
	next_point_index = 0 
	while next_point_index<len(costs):
		nondominated_point_mask = numpy.any(costs>costs[next_point_index], axis=1)
		nondominated_point_mask[next_point_index] = True
		is_efficient = is_efficient[nondominated_point_mask]
		costs = costs[nondominated_point_mask]
		next_point_index = numpy.sum(nondominated_point_mask[:next_point_index])+1
	return is_efficient


def paretoEfficient(costs):

	is_efficient = numpy.arange(costs.shape[0])
	n_points = costs.shape[0]
	next_point_index = 0
	while next_point_index<len(costs):
		nondominated_point_mask = numpy.any(costs>costs[next_point_index], axis=1)
		nondominated_point_mask[next_point_index] = True
		is_efficient = is_efficient[nondominated_point_mask]
		costs = costs[nondominated_point_mask]
		next_point_index = numpy.sum(nondominated_point_mask[:next_point_index])+1
	return is_efficient


def sffMapping(network_topology, service_topology, mapped_nodes_sf, mapping_nodes_sff, weigh_metrics):
	
	reversed_mapped_nodes_sf = {}
	for net_node in mapped_nodes_sf:
		for sf_inst in mapped_nodes_sf[net_node]:
				reversed_mapped_nodes_sf[sf_inst] = net_node

	reversed_mapping_nodes_sff = {}
	for sff_inst in mapping_nodes_sff:
		for sf_inst in mapping_nodes_sff[sff_inst]:
			if sf_inst in reversed_mapping_nodes_sff:
				reversed_mapping_nodes_sff[sf_inst].append(sff_inst)
			else:
				reversed_mapping_nodes_sff[sf_inst] = [sff_inst]

	sff_neighborhood = sffRelations(service_topology, mapping_nodes_sff, reversed_mapped_nodes_sf, reversed_mapping_nodes_sff)

	mapping_options = {sff_inst:[] for sff_inst in mapping_nodes_sff}
	for net_node in network_topology.nodes:
		for sff_inst in mapping_nodes_sff:
			if sffCandidate(network_topology, reversed_mapped_nodes_sf, net_node, mapping_nodes_sff[sff_inst]):
				mapping_options[sff_inst].append(net_node)

	evaluation_results = [[] for i in range(len(weigh_metrics)+1)]
	evaluate_mapping_options = list(itertools.product(*list(mapping_options.values())))
	print("\nSTARTING EVALUATION OF " + str(len(evaluate_mapping_options)) + " CANDIDATES!")
	candidate_index = 0
	for sff_mapping in evaluate_mapping_options:
		
		candidate_index += 1
		if candidate_index % 10000 == 0:
			print("EVALUATING:", candidate_index)

		if len(set(sff_mapping)) != len(sff_mapping):
			continue
		check_neighbors, sff_neighbors = sffNeighborhood(network_topology, mapping_nodes_sff, sff_neighborhood, sff_mapping)
		if not check_neighbors:
			continue

		curr_evaluation_result = sffEvaluate(network_topology, mapping_nodes_sff, sff_neighbors, reversed_mapped_nodes_sf, sff_mapping, 5)
		for index in range(len(curr_evaluation_result)):
			evaluation_results[index].append(curr_evaluation_result[index])
		evaluation_results[-1].append(sff_mapping)

	evaluation_scores = sffScoring(evaluation_results, weigh_metrics)
	best_index = evaluation_scores.index(max(evaluation_scores))
	best_candidate = (evaluation_results[-1][best_index], [evaluation_results[i][best_index] for i in range(len(weigh_metrics))], evaluation_scores[best_index])

	#===================================================
	#=========== UNCOMMENT ONLY FOR TESTS ==============
	'''np_results = []
	for index in range(len(evaluation_results[0])):
		if not [evaluation_results[0][index], evaluation_results[1][index]] in np_results:
			np_results.append([evaluation_results[0][index], evaluation_results[1][index]])
	
	np_results = numpy.array(np_results)
	np_candidates = numpy.array(evaluation_results[-1])

	fronts_file = open("frontiers_data.csv", "w+")
	fronts_index = 0
	while len(np_results) > 0:
		if fronts_index % 500 == 0:
			print("PARETO", fronts_index, ":", len(np_results))
		pareto_fronts = paretoEfficient(np_results)
		for index in pareto_fronts:
			fronts_file.write(str(int(np_results[index][0])) + ";" + str(round(np_results[index][1], 2)) + ";" + str(fronts_index) + "\n")
		np_results = numpy.delete(np_results, pareto_fronts, axis=0)
		np_candidates = numpy.delete(np_candidates, pareto_fronts, axis=0)
		fronts_index += 1
	print("PARETO", fronts_index, ":", len(np_results))
	fronts_file.close()'''
	#===================================================

	return best_candidate


def scCandidate(network_topology, sff_mapped, net_node):

	if "SC" in network_topology.nodes[net_node]:
		return False

	for sff_node in sff_mapped:
		if not networkx.has_path(network_topology, net_node, sff_node):
			return False

	return True


def scRank(network_topology, sff_mapped, sc_options, weigh_metrics, cut_off):
	
	maximum_self_degree = 0
	maximum_paths_degree = 0

	node_scores = {}
	for net_node in sc_options:
		self_degree = network_topology.degree[net_node]

		paths_degree_sum = 0
		for target_node in sff_mapped:
			for subgraph in networkx.all_simple_paths(network_topology, net_node, target_node, cutoff=cut_off):
				for node in subgraph:
					paths_degree_sum += network_topology.degree[node]

		if self_degree > maximum_self_degree:
			maximum_self_degree = self_degree
		if paths_degree_sum > maximum_paths_degree:
			maximum_paths_degree = paths_degree_sum
		node_scores[net_node] = (self_degree, paths_degree_sum)

	for net_node in node_scores:
		node_scores[net_node] = node_scores[net_node][0]/maximum_self_degree * weigh_metrics[0] + node_scores[net_node][1]/maximum_paths_degree * weigh_metrics[1]

	return {k: v for k, v in sorted(node_scores.items(), key=lambda item: item[1], reverse=True)}


def scMapping(network_topology, sff_mapped, classifiers_n, weigh_metrics):
	
	mapping_options = []
	for net_node in network_topology.nodes:
		if scCandidate(network_topology, sff_mapped, net_node):
			mapping_options.append(net_node)
	node_scores = scRank(network_topology, sff_mapped, mapping_options, weigh_metrics, 5)
	
	if len(node_scores) < classifiers_n:
		print("ERROR: UNABLE TO MAP ALL THE SC INSTANCES!")
		exit()

	sc_mapped = ([], [])
	node_keys = list(node_scores.keys())
	for index in range(classifiers_n):
		sc_mapped[0].append(node_keys[index])
		sc_mapped[1].append(node_scores[node_keys[index]])

	return sc_mapped 


def timingStatistics(t_results, t_rounds):

	mean_time = round(statistics.mean(t_results), 3)
	stdev_time =round(statistics.stdev(t_results), 3)

	output_file = open("timing_results_ILP.csv", "w+")
	output_file.write("parameter;value\n")
	output_file.write("t_rounds;" + str(t_rounds) + "\n\n")

	output_file.write("mean_time;" + str(mean_time) + "\n")
	output_file.write("stdev_time" + str(stdev_time) + "\n")
	output_file.close()


if len(sys.argv) != 6 and len(sys.argv) != 8:
	print("ERROR: INVALID ARGUMENTS! [*.py network_graphml service_graphml forwarders_graphml classifiers_n weigh_factor -t t_rounds]")
	exit()

network_topology = parseGraph(sys.argv[1])
service_topology = parseGraph(sys.argv[2])
forwarders_topology = parseGraph(sys.argv[3])

try:
	classifiers_n = int(sys.argv[4])
except:
	print("ERROR: INAVLID ARGUMENT OF classifiers_n PROVIDED!")
	exit()

try:
	weigh_values = (float(sys.argv[5]), 1 - float(sys.argv[5]))
except:
	print("ERROR: INAVLID ARGUMENT OF weigh_factor PROVIDED!")
	exit()

if weigh_values[0] > 1 or weigh_values[0] < 0:
	print("ERROR: INAVLID weigh_factor VALUE PROVIDED!")
	exit()

t_rounds = 1
if len(sys.argv) == 8:

	if sys.argv[6] != "-t":
		print("ERROR: INVALID ARGUMENTS! [*.py network_graphml service_graphml forwarders_graphml classifiers_n weigh_factor -t t_rounds]")
		exit()

	try:
		t_rounds = int(sys.argv[7])
	except:
		print("ERROR: INAVLID ARGUMENT OF t_rounds PROVIDED!")
		exit()

mapped_nodes_sf, mapping_nodes_sff, relation_sf_sff, basic_sff_mapping = checkPremises(network_topology, service_topology, forwarders_topology, classifiers_n)
basicMapping(network_topology, basic_sff_mapping)
for sff in list(basic_sff_mapping.values()):
	mapping_nodes_sff.pop(sff)

t_results = []
for r in range(t_rounds):
	start_time = time.time()
	sff_mapped = sffMapping(network_topology, service_topology, mapped_nodes_sf, mapping_nodes_sff, weigh_values)
	sc_mapped = scMapping(network_topology, sff_mapped[0], classifiers_n, weigh_values)
	t_results.append(time.time() - start_time)
	print("ROUND", r, "-", t_results[-1])

if t_rounds > 1:
	timingStatistics(t_results, t_rounds)

print("\n", sff_mapped, "\n", sc_mapped)

