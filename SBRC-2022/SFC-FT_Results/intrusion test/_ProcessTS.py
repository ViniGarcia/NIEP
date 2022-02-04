import statistics


test_list = [("time_sheet_client_b1_02.csv", "time_sheet_server_b1_02.csv"), ("time_sheet_client_b2_03.csv", "time_sheet_server_b2_03.csv"), ("time_sheet_client_b3_04.csv", "time_sheet_server_b3_04.csv"), ("time_sheet_client_b4_05.csv", "time_sheet_server_b4_05.csv"), ("time_sheet_client_b6_06.csv", "time_sheet_server_b6_06.csv"), ("time_sheet_client_b8_07.csv", "time_sheet_server_b8_07.csv")]


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