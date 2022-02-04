import statistics

client_file = open("time_sheet_client_1024_7elem.csv", "r")
server_file = open("time_sheet_server_1024_7elem.csv", "r")

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
for index in range(len(client_dict)):
	delay_list.append(server_dict[index] - client_dict[index])

print("mean;" + str(round(statistics.mean(delay_list), 3)))
print("stdev;" + str(round(statistics.stdev(delay_list), 3)))