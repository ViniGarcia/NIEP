import sys
import csv
import copy
import time
import random
import bisect
import networkx
import platypus
import statistics

#########################################################################################################################################
##################################################### GENETIC STRATEGY - RESOURCES ######################################################
#########################################################################################################################################

class mapperGenerator(platypus.Generator):

	__network_topology = None
	__sff_neighborhood = None
	__sff_mappings = None


	def __init__(self, network_topology, sff_neighborhood, sff_mappings):

		super(mapperGenerator, self).__init__()
		self.__network_topology = network_topology
		self.__network_nodes = list(network_topology.nodes)
		self.__sff_neighborhood = sff_neighborhood
		self.__sff_mappings = sff_mappings
		self.__sff_keys = list(sff_mappings.keys())

		self.__data_translator = platypus.Integer(0, len(network_topology.nodes)-1)


	def generate(self, problem):

		forming_solution = [self.__sff_mappings[self.__sff_keys[0]][random.randint(0, len(self.__sff_mappings[self.__sff_keys[0]])-1)]]
		for sff_index in range(1, len(self.__sff_keys)):
			
			checked_mappings = []
			while len(self.__sff_mappings[self.__sff_keys[sff_index]]) > 0:
				checked_mappings.append(self.__sff_mappings[self.__sff_keys[sff_index]].pop(random.randint(0, len(self.__sff_mappings[self.__sff_keys[sff_index]])-1)))
				control_flag = True

				if checked_mappings[-1] in forming_solution:
					control_flag = False
					continue

				if self.__sff_keys[sff_index] in self.__sff_neighborhood:
					for sff_neighbor in self.__sff_neighborhood[self.__sff_keys[sff_index]]:
						if self.__sff_keys.index(sff_neighbor) < sff_index:
							if not networkx.has_path(network_topology, checked_mappings[-1], forming_solution[self.__sff_keys.index(sff_neighbor)]):
								control_flag = False
								break

				if control_flag:
					forming_solution.append(checked_mappings[-1])
					break 

			self.__sff_mappings[self.__sff_keys[sff_index]] += checked_mappings
			if not control_flag:
				return self.generate(problem)

		solution = platypus.Solution(problem)
		solution.variables = [self.__data_translator.encode(self.__network_nodes.index(node)) for node in forming_solution]
		return solution


class mapperCrossover(platypus.Variator):

	__network_topology = None
	__sff_neighborhood = None
	__probability = None

	def __init__(self, network_topology, sff_neighborhood, sff_mappings, probability):
		
		super(mapperCrossover, self).__init__(2)
		self.__network_topology = network_topology
		self.__network_nodes = list(network_topology.nodes)
		self.__sff_neighborhood = sff_neighborhood
		self.__sff_mappings = sff_mappings
		self.__sff_keys = list(sff_mappings.keys())
		self.__probability = probability

		self.__data_translator = platypus.Integer(0, len(network_topology.nodes)-1)


	def validate(self, candidate, crossover_index):

		control_flag = True
		for sff_index in range(crossover_index, len(self.__sff_keys)):
			if candidate.variables.count(candidate.variables[sff_index]) > 1:
				control_flag = False
				break

			if self.__sff_keys[sff_index] in self.__sff_neighborhood:
				for sff_neighbor in self.__sff_neighborhood[self.__sff_keys[sff_index]]:
					if self.__sff_keys.index(sff_neighbor) < crossover_index:
						if not networkx.has_path(network_topology, self.__network_nodes[self.__data_translator.decode(candidate.variables[sff_index])], self.__network_nodes[self.__data_translator.decode(candidate.variables[self.__sff_keys.index(sff_neighbor)])]):
							control_flag = False
							break
		
		return control_flag


	def evolve(self, parents):

		result1 = copy.deepcopy(parents[0])
		result2 = copy.deepcopy(parents[1])
		problem = result1.problem

		if random.uniform(0.0, 1.0) <= self.__probability:

			crossover_eval = ([network_topology.degree[self.__network_nodes[self.__data_translator.decode(result1.variables[0])]]], [network_topology.degree[self.__network_nodes[self.__data_translator.decode(result2.variables[problem.nvars - 1])]]])
			for index in range(1, problem.nvars - 1):
				crossover_eval[0].append(network_topology.degree[self.__network_nodes[self.__data_translator.decode(result1.variables[index])]] + crossover_eval[0][-1])
				crossover_eval[1].insert(0, network_topology.degree[self.__network_nodes[self.__data_translator.decode(result2.variables[problem.nvars - index - 1])]] + crossover_eval[1][0])

			crossover_sum = []
			crossover_key = []
			for index in range(len(crossover_eval[0])):
				bisect.insort(crossover_sum, crossover_eval[0][index] + crossover_eval[1][index])
				crossover_key.insert(crossover_sum.index(crossover_eval[0][index] + crossover_eval[1][index]), index + 1)

			success_flag = True
			for index in range(len(crossover_key) - 1, -1, -1):
				result1.variables[:] = parents[0].variables[:crossover_key[index]] + parents[1].variables[crossover_key[index]:]
				result2.variables[:] = parents[1].variables[:crossover_key[index]] + parents[0].variables[crossover_key[index]:]
				if not self.validate(result1, crossover_key[index]) or not self.validate(result2, crossover_key[index]):
					success_flag = False
				else:
					break

			if success_flag:
				result1.evaluated = False
				result2.evaluated = False
				return [result1, result2]

		return [parents[0], parents[1]]


class mapperMutation(platypus.Mutation):

	__network_topology = None
	__sff_neighborhood = None
	__sff_mappings = None
	__probability = None


	def __init__(self, network_topology, sff_neighborhood, sff_mappings, probability):

		super(mapperMutation, self).__init__()
		self.__network_topology = network_topology
		self.__network_nodes = list(network_topology.nodes)
		self.__sff_neighborhood = sff_neighborhood
		self.__sff_mappings = sff_mappings
		self.__sff_keys = list(sff_mappings.keys())
		self.__probability = probability

		self.__data_translator = platypus.Integer(0, len(network_topology.nodes)-1)


	def mutate(self, parent):

		mutation_result = copy.deepcopy(parent)
		control_flag = False
		if random.uniform(0.0, 1.0) <= self.__probability:
			mutating_postion = random.randint(0, len(mutation_result.variables)-1)

			checked_mappings = []
			while len(self.__sff_mappings[self.__sff_keys[mutating_postion]]) > 0:
				checked_mappings.append(self.__sff_mappings[self.__sff_keys[mutating_postion]].pop(random.randint(0, len(self.__sff_mappings[self.__sff_keys[mutating_postion]])-1)))
				control_flag = True

				if self.__sff_keys[mutating_postion] in self.__sff_neighborhood:
					for sff_neighbor in self.__sff_neighborhood[self.__sff_keys[mutating_postion]]:
						if not networkx.has_path(network_topology, checked_mappings[-1], self.__network_nodes[self.__data_translator.decode(mutation_result.variables[self.__sff_keys.index(sff_neighbor)])]):
							control_flag = False
							break
				
				if control_flag:
					mutation_result.variables[mutating_postion] = self.__data_translator.encode(self.__network_nodes.index(checked_mappings[-1]))
					if mutation_result.variables.count(mutation_result.variables[mutating_postion]) > 1:
						control_flag = False
						continue
					break

			self.__sff_mappings[self.__sff_keys[mutating_postion]] += checked_mappings

		if control_flag:
			mutation_result.evaluated = False
			return mutation_result
		else:
			return parent


class mapperProblem(platypus.Problem):

	__network_topology = None
	__sff_instances = None
	__sff_neighborhood = None
	__sf_mapping = None
	__cut_off = None


	def __init__(self, network_topology, sff_instances, sff_neighborhood, sf_mapping, cut_off):

		super(mapperProblem, self).__init__(len(sff_instances), 2)
		self.types[:] = [platypus.Integer(0, len(network_topology.nodes)-1)] * len(sff_instances)
		self.directions[:] = [platypus.Problem.MAXIMIZE, platypus.Problem.MAXIMIZE]

		self.__network_topology = network_topology
		self.__network_nodes = list(network_topology.nodes)
		self.__sff_instances = sff_instances
		self.__sff_keys = list(sff_instances.keys())
		self.__sff_neighborhood = sff_neighborhood
		self.__sf_mapping = sf_mapping
		self.__cut_off = cut_off

	def evaluate(self, solution):
		
		self_degree_sum = 0
		paths_degree_sum = 0

		for sff_index in range(len(self.__sff_keys)):
			self_degree_sum += network_topology.degree[self.__network_nodes[solution.variables[sff_index]]]

			for target_node in self.__sff_instances[self.__sff_keys[sff_index]]: #SFs
				for subgraph in networkx.all_simple_paths(network_topology, self.__network_nodes[solution.variables[sff_index]], target_node, cutoff=self.__cut_off):
					tmp_paths_degree_sum = 0
					for node in subgraph:
						tmp_paths_degree_sum += network_topology.degree[node]
					paths_degree_sum += tmp_paths_degree_sum / len(subgraph)


			if self.__sff_keys[sff_index] in self.__sff_neighborhood:
				for target_node in self.__sff_neighborhood[self.__sff_keys[sff_index]]: #SFFs
						for subgraph in networkx.all_simple_paths(network_topology, self.__network_nodes[solution.variables[sff_index]], self.__network_nodes[solution.variables[self.__sff_keys.index(target_node)]], cutoff=self.__cut_off):
							tmp_paths_degree_sum = 0
							for node in subgraph:
								tmp_paths_degree_sum += network_topology.degree[node]
							paths_degree_sum += tmp_paths_degree_sum / len(subgraph)

		solution.objectives[:] = [self_degree_sum, paths_degree_sum]

#########################################################################################################################################
#########################################################################################################################################
#########################################################################################################################################


#########################################################################################################################################
###################################################### MAPPING BASICS - ALGORITHMS ######################################################
#########################################################################################################################################

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


def sffCandidate(network_topology, reversed_mapped_nodes_sf, net_node, sff_inst):

	if "SFF" in network_topology.nodes[net_node]:
		return False

	for sf_inst in sff_inst:
		if not networkx.has_path(network_topology, net_node, reversed_mapped_nodes_sf[sf_inst]):
			return False

	return True


def sffOptions(network_topology, mapping_nodes_sff, reversed_mapped_nodes_sf):

	mapping_options = {sff_inst:[] for sff_inst in mapping_nodes_sff}
	for net_node in network_topology.nodes:
		for sff_inst in mapping_nodes_sff:
			if sffCandidate(network_topology, reversed_mapped_nodes_sf, net_node, mapping_nodes_sff[sff_inst]):
				mapping_options[sff_inst].append(net_node)

	return mapping_options


def sffRelations(service_topology, mapping_nodes_sff, reversed_mapping_nodes_sff):

	sff_check_neighborhood = {}
	for sff_node in mapping_nodes_sff:
		sff_check_neighborhood[sff_node] = []
		for sf_node in mapping_nodes_sff[sff_node]:
			for sf_neigh in service_topology.neighbors(sf_node):
				if not sf_neigh in mapping_nodes_sff[sff_node]:
					sff_check_neighborhood[sff_node] += reversed_mapping_nodes_sff[sf_neigh]

	return sff_check_neighborhood


def sffScoring(evaluation_results, weigh_metrics):

	scoring_results = [0] * len(evaluation_results)
	metrics_paratmeter = [0] * len(weigh_metrics)

	for result_candidate in evaluation_results:
		for metric_index in range(len(metrics_paratmeter)):
			if result_candidate.objectives[metric_index] > metrics_paratmeter[metric_index]:
				metrics_paratmeter[metric_index] = result_candidate.objectives[metric_index]

	for metric_index in range(len(weigh_metrics)):
		for result_index in range(len(evaluation_results)):
			scoring_results[result_index] += evaluation_results[result_index].objectives[metric_index] / metrics_paratmeter[metric_index] * weigh_metrics[metric_index]

	return scoring_results


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


def main(ga_rounds, ga_population, ga_crossover, ga_mutation, network_topology, mapping_nodes_sff, possibilities_sff, neighborhood_sff, mapped_nodes_sf, classifiers_n, weigh_metrics):

	mapping_generator = mapperGenerator(network_topology, neighborhood_sff, possibilities_sff)
	mapping_crossover = mapperCrossover(network_topology, neighborhood_sff, possibilities_sff, ga_crossover)
	mapping_mutation = mapperMutation(network_topology, neighborhood_sff, possibilities_sff, ga_mutation)
	mapping_problem = mapperProblem(network_topology, mapping_nodes_sff, neighborhood_sff, mapped_nodes_sf, 5)

	mapping_algorithm = platypus.NSGAII(mapping_problem, population_size = ga_population, generator = mapping_generator, selector = platypus.operators.TournamentSelector(2), variator = platypus.operators.GAOperator(mapping_crossover, mapping_mutation))
	mapping_algorithm.run(ga_rounds)
	
	data_translator = platypus.Integer(0, len(network_topology.nodes)-1)	
	network_nodes = list(network_topology.nodes)

	sff_evaluation_results = platypus.nondominated(mapping_algorithm.result)
	sff_mapping_scores = sffScoring(sff_evaluation_results, weigh_metrics)
	sff_best_index = sff_mapping_scores.index(max(sff_mapping_scores))
	sff_evaluation_results[sff_best_index].variables =  [network_nodes[data_translator.decode(r)] for r in sff_evaluation_results[sff_best_index].variables]

	sc_evaluation_results = scMapping(network_topology, sff_evaluation_results[sff_best_index].variables, classifiers_n, weigh_metrics)

	return (sff_evaluation_results[sff_best_index], sc_evaluation_results)

#########################################################################################################################################
#########################################################################################################################################
#########################################################################################################################################


#########################################################################################################################################
############################################################ EXPERIMENTS AREA ###########################################################
#########################################################################################################################################

def paretoOrganize(experiment_results, reference_file):

	reference_file = open(reference_file, "r")
	reference_csv = csv.reader(reference_file, delimiter=';')
	
	eval_dict = {}
	for row in reference_csv:
		if int(row[0]) in eval_dict:
			eval_dict[int(row[0])][float(row[1])] = int(row[-1])
		else:
			eval_dict[int(row[0])] = {float(row[1]):int(row[-1])}

	res_dicts = []
	for exec_round in experiment_results:
		
		res_dicts.append({})
		for index in range(len(exec_round[1])):
			
			candidate = (int(exec_round[1][index][0]), round(exec_round[1][index][1], 2))
			try:
				if eval_dict[candidate[0]][candidate[1]] in res_dicts[-1]:
					if not tuple((exec_round[0][index][0], exec_round[0][index][1])) in res_dicts[-1][eval_dict[candidate[0]][candidate[1]]]:
						res_dicts[-1][eval_dict[candidate[0]][candidate[1]]].append(tuple((exec_round[0][index][0], exec_round[0][index][1])))
				else:
					res_dicts[-1][eval_dict[candidate[0]][candidate[1]]] = [tuple((exec_round[0][index][0], exec_round[0][index][1]))]
			except:
				print("ERROR:", candidate, "!!")
				exit()

	reference_file.close()

	return res_dicts 


def paretoMain(reference_file, p_step, ga_rounds, ga_population, ga_crossover, ga_mutation, network_topology, mapping_nodes_sff, possibilities_sff, neighborhood_sff, mapped_nodes_sf, classifiers_n, weigh_metrics):

	mapping_generator = mapperGenerator(network_topology, neighborhood_sff, possibilities_sff)
	mapping_crossover = mapperCrossover(network_topology, neighborhood_sff, possibilities_sff, ga_crossover)
	mapping_mutation = mapperMutation(network_topology, neighborhood_sff, possibilities_sff, ga_mutation)
	mapping_problem = mapperProblem(network_topology, mapping_nodes_sff, neighborhood_sff, mapped_nodes_sf, 5)

	mapping_algorithm = platypus.NSGAII(mapping_problem, population_size = ga_population, generator = mapping_generator, selector = platypus.operators.TournamentSelector(2), variator = platypus.operators.GAOperator(mapping_crossover, mapping_mutation))

	last = []
	results = []
	while ga_rounds > 0:
		#self.__algorithm.nfe = False #Reset the algorithm population -- only for particular tests
			
		if p_step < ga_rounds:
			mapping_algorithm.run(p_step)
			ga_rounds -= p_step
		else:
			mapping_algorithm.run(ga_rounds)
			ga_rounds = 0

		final = [[], []]
		nondominated = platypus.nondominated(mapping_algorithm.result)

		for solution in nondominated:
			if not solution.variables in final[0] and solution.feasible:
				final[0].append(copy.deepcopy(solution.variables))
				final[1].append(copy.deepcopy(solution.objectives))

		'''
		check = copy.deepcopy(final[0])
		check.sort()

		if last == check:
			break
		last = check
		'''

		results.append(final)

	data_translator = platypus.Integer(0, len(network_topology.nodes)-1)
	network_nodes = list(network_topology.nodes)
	for exec_round in results:
		for candidate in exec_round[0]:
			for index in range(len(candidate)):
				candidate[index] = network_nodes[data_translator.decode(candidate[index])]

	return paretoOrganize(results, reference_file)


def timingStatistics(t_results, t_rounds, ga_rounds, ga_population, ga_crossover, ga_mutation):

	mean_time = round(statistics.mean(t_results), 3)
	stdev_time =round(statistics.stdev(t_results), 3)

	output_file = open("timing_results_GA.csv", "w+")
	output_file.write("parameter;value\n")
	output_file.write("ga_rounds;" + str(ga_rounds) + "\n")
	output_file.write("ga_population;" + str(ga_population) + "\n")
	output_file.write("ga_crossover;" + str(ga_crossover) + "\n")
	output_file.write("ga_mutation;" + str(ga_mutation) + "\n")
	output_file.write("t_rounds;" + str(t_rounds) + "\n\n")

	output_file.write("mean_time;" + str(mean_time) + "\n")
	output_file.write("stdev_time" + str(stdev_time) + "\n")
	output_file.close()


def paretoStatistics(p_results, p_rounds, p_step, ga_rounds, ga_population, ga_crossover, ga_mutation):

	output_file = open("pareto_results_GA.csv", "w+")
	output_file.write("parameter;value\n")
	output_file.write("ga_rounds;" + str(ga_rounds) + "\n")
	output_file.write("ga_population;" + str(ga_population) + "\n")
	output_file.write("ga_crossover;" + str(ga_crossover) + "\n")
	output_file.write("ga_mutation;" + str(ga_mutation) + "\n")
	output_file.write("p_rounds;" + str(p_rounds) + "\n\n")
	output_file.write("p_step;" + str(p_step) + "\n\n")

	for s_index in range(len(p_results[0])):
		r_frontiers = []
		for r_index in range(p_rounds):
			for key in p_results[r_index][s_index]:
				r_frontiers += [key for i in range(len(p_results[r_index][s_index][key]))]
		output_file.write(str(s_index) + ";" + str(statistics.mean(r_frontiers)) + ";" + str(statistics.stdev(r_frontiers)) + ";" + str(max(r_frontiers)) + ";" + str(min(r_frontiers)) + "\n")
	output_file.close()

def paretoExperiment(p_file, p_rounds, p_step, ga_rounds, ga_population, ga_crossover, ga_mutation, network_topology, mapping_nodes_sff, possibilities_sff, neighborhood_sff, mapped_nodes_sf, classifiers_n, weigh_metrics):

	p_results = []
	for r in range(p_rounds):
		p_results.append(paretoMain(p_file, p_step, ga_rounds, ga_population, ga_crossover, ga_mutation, network_topology, mapping_nodes_sff, possibilities_sff, neighborhood_sff, mapped_nodes_sf, classifiers_n, weigh_values))

	paretoStatistics(p_results, p_rounds, p_step, ga_rounds, ga_population, ga_crossover, ga_mutation)


def timeExperiment(t_rounds, ga_rounds, ga_population, ga_crossover, ga_mutation, network_topology, mapping_nodes_sff, possibilities_sff, neighborhood_sff, mapped_nodes_sf, classifiers_n, weigh_metrics):

	t_results = []
	for r in range(t_rounds):
		start_time = time.time()
		main(ga_rounds, ga_population, ga_crossover, ga_mutation, network_topology, mapping_nodes_sff, possibilities_sff, neighborhood_sff, mapped_nodes_sf, classifiers_n, weigh_values)
		t_results.append(time.time() - start_time)

	timingStatistics(t_results, t_rounds, ga_rounds, ga_population, ga_crossover, ga_mutation)

#########################################################################################################################################
#########################################################################################################################################
#########################################################################################################################################


#########################################################################################################################################
################################################################## MAIN #################################################################
#########################################################################################################################################

if len(sys.argv) < 10:
	print("ERROR: INVALID ARGUMENTS! [*.py network_graphml service_graphml forwarders_graphml classifiers_n weigh_factor ga_population ga_crossover ga_mutation ga_rounds (-t t_rounds/-p p_step p_rounds p_file)")
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

try: 
	ga_population = int(sys.argv[6])
except:
	print("ERROR: INAVLID ARGUMENT OF ga_population PROVIDED!")
	exit()

try: 
	ga_crossover = float(sys.argv[7])
except:
	print("ERROR: INAVLID ARGUMENT OF ga_crossover PROVIDED!")
	exit()

try: 
	ga_mutation = float(sys.argv[8])
except:
	print("ERROR: INAVLID ARGUMENT OF ga_mutation PROVIDED!")
	exit()

try: 
	ga_rounds = int(sys.argv[9])
except:
	print("ERROR: INAVLID ARGUMENT OF ga_rounds PROVIDED!")
	exit()

if len(sys.argv) > 10:
	if sys.argv[10] == "-t":
		if len(sys.argv) != 12:
			print("ERROR: INVALID ARGUMENTS! [*.py network_graphml service_graphml forwarders_graphml classifiers_n weigh_factor ga_population ga_crossover ga_mutation ga_rounds (-t t_rounds/-p p_step p_rounds p_file)")	
			exit()

		try: 
			t_rounds = int(sys.argv[11])
		except:
			print("ERROR: INAVLID ARGUMENT OF t_rounds PROVIDED!")
			exit()

		mode = 1

	elif sys.argv[10] == "-p":
		if len(sys.argv) != 14:
			print("ERROR: INVALID ARGUMENTS! [*.py network_graphml service_graphml forwarders_graphml classifiers_n weigh_factor ga_population ga_crossover ga_mutation ga_rounds (-t t_rounds/-p p_step p_rounds p_file)")
			exit()

		try:
			p_step = int(sys.argv[11])
		except:
			print("ERROR: INAVLID ARGUMENT OF p_step PROVIDED!")
			exit()

		try:
			p_rounds = int(sys.argv[12])
		except:
			print("ERROR: INAVLID ARGUMENT OF p_rounds PROVIDED!")
			exit()

		p_file = sys.argv[13]

		mode = 2

	else:
		print("ERROR: INAVLID mode PROVIDED!")
		exit()
else:
	mode = 0 

mapped_nodes_sf, mapping_nodes_sff, relation_sf_sff, basic_sff_mapping = checkPremises(network_topology, service_topology, forwarders_topology, classifiers_n)
basicMapping(network_topology, basic_sff_mapping)

for sff in list(basic_sff_mapping.values()):
	mapping_nodes_sff.pop(sff)

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

neighborhood_sff = sffRelations(service_topology, mapping_nodes_sff, reversed_mapping_nodes_sff)
possibilities_sff = sffOptions(network_topology, mapping_nodes_sff, reversed_mapped_nodes_sf)

if mode == 0:
	main(ga_rounds, ga_population, ga_crossover, ga_mutation, network_topology, mapping_nodes_sff, possibilities_sff, neighborhood_sff, mapped_nodes_sf, classifiers_n, weigh_values)
elif mode == 1:
	timeExperiment(t_rounds, ga_rounds, ga_population, ga_crossover, ga_mutation, network_topology, mapping_nodes_sff, possibilities_sff, neighborhood_sff, mapped_nodes_sf, classifiers_n, weigh_values)
else:
	paretoExperiment(p_file, p_rounds, p_step, ga_rounds, ga_population, ga_crossover, ga_mutation, network_topology, mapping_nodes_sff, possibilities_sff, neighborhood_sff, mapped_nodes_sf, classifiers_n, weigh_values)

#########################################################################################################################################
#########################################################################################################################################
#########################################################################################################################################