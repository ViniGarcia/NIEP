import statistics


test_list = [("client-aw-01.csv", "server-aw-01.csv"), ("client-f1-02.csv", "server-f1-02.csv"), ("client-f2-03.csv", "server-f2-03.csv"), ("client-f3-04.csv", "server-f3-04.csv"), ("client-f4-05.csv", "server-f4-05.csv"), ("client-f6-06.csv", "server-f6-06.csv"), ("client-f8-07.csv", "server-f8-07.csv")]


for test in test_list:
	client_file = open(test[0], "r")
	server_file = open(test[1], "r")

	client_dict = {}
	for line in client_file:
		if len(line) > 0:
			line = line.split(";")
			client_dict[int(line[0])] = float(line[1])

	server_dict = {}
	for line in server_file:
		if len(line) > 0:
			line = line.split(";")
			server_dict[int(line[0])] = float(line[1])

	delay_list = []
	for index in sorted(list(client_dict.keys())):
		delay_list.append(server_dict[index] - client_dict[index])

	print("mean;" + str(round(statistics.mean(delay_list), 3)))
	print("stdev;" + str(round(statistics.stdev(delay_list), 3)))

	client_file.close()
	server_file.close()