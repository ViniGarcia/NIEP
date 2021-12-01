import requests
import yaml
import sys
import re

def isIP(potential_ip):
    return re.match("[0-9]+(?:\\.[0-9]+){3}", potential_ip.lower())

def configure(sfp_yaml, sc_ip, sff_configure):

    try:
        yaml_file = open(sfp_yaml, "r")
    except:
        print("ERROR: INVALID SFP YAML FILE PATH PROVIDED!")
        exit()
    
    try:
        yaml_data = yaml.safe_load(yaml_file)
    except:
        print("ERROR: INVALID SFP YAML STRUCTURE PROVIDED!")
        exit()
        

    response = requests.post("http://" + sc_ip + ":8080/setup", {"sfp_yaml": yaml.dump(yaml_data), "sff_configure":sff_configure})
    print("SC SETUP: ", response, response.content, "\n")


def delete(sc_ip, sfp_id):
    
    response = requests.post("http://" + sc_ip + ":8080/delete", {"sfp_id": sfp_id})
    print("SC DELETE: ", response, "\n")    

def start(sc_ip):

    response = requests.post("http://" + sc_ip + ":8080/start")
    print("SC START: ", response, "\n")

def status(sc_ip):

    response = requests.get("http://" + sc_ip + ":8080/status")
    print("SC STATUS: ", response, "\n")

if len(sys.argv) == 4:
    sc_acc_address = sys.argv[1]
    sfp_file_path = sys.argv[2]
    sfp_id = sys.argv[3]
else:
    print("ERROR: INVALID ARGUMENTS PROVIDED! [EXPECTED: Manager.py SC_ACC_ADDRESS SFP_FILE_PATH SFP_ID]")
    exit()

if not isIP(sc_acc_address):
    print("ERROR: INVALID SC IP PROVIDED!")
    exit()

while True:
    action = input("Enter action: ")
    if action == "configure1":
        configure(sfp_file_path, sc_acc_address, True)
    if action == "configure2":
        configure(sfp_file_path, sc_acc_address, False)
    elif action == "start":
        start(sc_acc_address)
    elif action == "status":
        status(sc_acc_address)
    elif action == "delete":
        delete(sc_acc_address, sfp_id)
