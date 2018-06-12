from requests import get
from requests import post
from requests import put
import json

dictionaryDomain = {"DOMAIN":{"IGP":"600", "EGP":"601"}}
dictionarySfc = {"SFC":{"FILE":"sfcteste.json", "DATA":'{"ID": "sfc","VNFS": [{"ID":"x","PATH":"x.json"}, {"ID":"y","PATH":"y.json"}, {"ID":"z","PATH":"z.json"}],"IP" : {"ID":"IP","LINK":"br0"},"OPS" : [{"ID":"OP1","LINK":"br5"}],"CONNECTIONS": [{"OLL":"IP","ILL":"x","ILL_MAC":"52:54:00:6c:22:13"},{"LINK":"br1","OLL": "x","OLL_MAC":"52:54:00:6c:22:14","ILL": "y","ILL_MAC":"52:54:00:6c:22:15"},{"LINK":"br2","OLL": "y","OLL_MAC":"52:54:00:6c:22:16","ILL": "z","ILL_MAC":"52:54:00:6c:22:17"},{"OLL":"z","OLL_MAC":"52:54:00:6c:22:18","ILL":"OP1"}]}'}}
dictionaryVnfs = {"VNFS":{"x.json":'{"ID": "x","MEMORY": 300,"VCPU": 1,"MANAGEMENT_MAC": "52:54:01:6c:22:01","INTERFACES": [{"ID": "br0","MAC": "52:54:00:6c:22:13"},{"ID": "br1","MAC": "52:54:00:6c:22:14"}]}', "y.json":'{"ID": "y","MEMORY": 300,"VCPU": 1,"MANAGEMENT_MAC": "52:54:01:6c:22:02","INTERFACES": [{"ID": "br1","MAC": "52:54:00:6c:22:15"},{"ID": "br2","MAC": "52:54:00:6c:22:16"}]}', "z.json":'{"ID": "z","MEMORY": 300,"VCPU": 1,"MANAGEMENT_MAC": "52:54:01:6c:22:03","INTERFACES": [{"ID": "br2","MAC": "52:54:00:6c:22:17"},{"ID": "br3","MAC": "52:54:00:6c:22:18"}]}'}}

dictionaryMain = {}
dictionaryMain["DOMAIN"] = dictionaryDomain["DOMAIN"]
dictionaryMain["SFC"] = dictionarySfc["SFC"]
dictionaryMain["VNFS"] = dictionaryVnfs["VNFS"]


response = post('http://localhost:8152/topology/creation/', data = json.dumps(dictionaryMain))
print response.text

response = get('http://localhost:8152/topology/instantiation/')
print response.text 

atype = None
atype = raw_input("action type: ")
while atype != '':
	action = raw_input("action: ")

	if atype == 'vnf':
		info = raw_input("element id: ")
		if action == 'action':
			info = [info]
			info.append(raw_input("action req: "))
			if info[1] == 'replace':
				info.append(raw_input("replace: "))
			str(info)

		response = post('http://localhost:8152/' + atype + '/' + action + '/', data = info)
	
	else:
		response = get('http://localhost:8152/' + atype + '/' + action + '/')
			
	print response.text
	atype = None
	atype = raw_input("action type: ")

response = get('http://localhost:8152/topology/termination/')
print response.text 

response = get('http://localhost:8152/topology/deletation/')
print response.text