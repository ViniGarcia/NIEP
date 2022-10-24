import requests
import yaml
import sys
import re

#Function that returns True if a given string represents and IPv4 without netmask, and return False otherwise
def isIP(potential_ip):
    return re.match("[0-9]+(?:\\.[0-9]+){3}", potential_ip.lower())


#Function that triggers the configuration of a particular SC
#  - sfp_yaml: yaml file that cointais the aimed SFP specification
#  - sc_ip: IPv4 address of the target SC instance
#  - sff_configure: bollean that indicates if the SC should configure the SFFs (True) or not (False)
def configure(sfp_yaml, sc_ip, sff_configure):

    try:
        yaml_file = open(sfp_yaml, "r")
    except:
        print("ERROR: INVALID SFP YAML FILE PATH PROVIDED!")
        exit()
    
    try:
        yaml_data = yaml.safe_load(yaml_file)
    except Exception as e:
        print(e)
        print("ERROR: INVALID SFP YAML STRUCTURE PROVIDED!")
        exit()
        

    response = requests.post("http://" + sc_ip + ":8080/setup", {"sfp_yaml": yaml.dump(yaml_data), "sff_configure":sff_configure})
    print("SC SETUP: ", response, response.content, "\n")


def test(sfp_yaml):

    configure(sfp_yaml, "192.168.123.1", True)
    start("192.168.123.1")
    for ip in ["192.168.123.2", "192.168.123.3", "192.168.123.4"]:
        configure(sfp_yaml, ip, False)
        start(ip)


#Function that triggers the remotion of a given SFP from a particular SC
#  - sc_ip: IPv4 address of the target SC instance
#  - sfp_id: id of the target SFP to remove
#  - sff_configure: bollean that indicates if the SC should configure the SFFs (True) or not (False)
def delete(sc_ip, sfp_id, sff_configure):
    
    response = requests.post("http://" + sc_ip + ":8080/delete", {"sfp_id": sfp_id, "sff_configure":sff_configure})
    print("SC DELETE: ", response, "\n")    


#Function that triggers the server start of a given SC instance
#  - sc_ip: IPv4 address of the target SC instance
def start(sc_ip):

    response = requests.post("http://" + sc_ip + ":8080/start")
    print("SC START: ", response, "\n")


#Function that requires the status of a given SC instance
#  - sc_ip: IPv4 address of the target SC instance
def status(sc_ip):

    response = requests.get("http://" + sc_ip + ":8080/status")
    print("SC STATUS: ", response, "\n")


#Function that tries to turn off a given SC instance
# - sc_ip: IPv4 address of the target SC instance
def stop(sc_ip):

    response = requests.post("http://" + sc_ip + ":8080/stop")
    print("SC STATUS: ", response, "\n")

#Main function that read arguments from the standard input and start the manager's server
#Available operations in the server:
# - configure_std: configure the SFP into the SC instance and related SFFs
# - configure_solo: configure the SFP only into the SC instance
# - start: start the SC instance server
# - staus: get the SC instance server status
# - delte_std: delete the SFP from the SC instance and related SFFs
# - delete_solo: delete the SFP only form the SC
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
    if action == "configure_std":
        configure(sfp_file_path, sc_acc_address, True)
    if action == "configure_solo":
        configure(sfp_file_path, sc_acc_address, False)
    elif action == "start":
        start(sc_acc_address)
    elif action == "status":
        status(sc_acc_address)
    elif action == "delete_std":
        delete(sc_acc_address, sfp_id, True)
    elif action == "delete_solo":
        delete(sc_acc_address, sfp_id, False)
    elif action == "stop":
        stop(sc_acc_address)
    elif action == "test":
        test(sfp_file_path)
