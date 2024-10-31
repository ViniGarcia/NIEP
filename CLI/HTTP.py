import os
import sys
import time
import flask
import signal
import psutil
import shutil
import zipfile
import os.path
import ipaddress
import subprocess

NIEPPROCESS = None
NIEPTIME = None
APP = flask.Flask(__name__)

################################################################# COMMON ################################################################

def up(arguments):
	global NIEPTIME
	global NIEPPROCESS

	if NIEPPROCESS != None:
		if not NIEPPROCESS.pid in [p.pid for p in psutil.process_iter()]:
			NIEPPROCESS = None
		else:
			return "NIEP ALREADY UP", 405	
	if not "path" in arguments:
		return "NO FILE PATH PROVIDED!", 400
	if not os.path.isfile(arguments["path"]):
		return "INVALID FILE PATH PROVIDED", 400

	try:	
		NIEPTIME = time.time()		
		NIEPPROCESS = subprocess.Popen(["gnome-terminal", "--", "python2.7", "Launcher.py", arguments["path"]])
		NIEPPROCESS.wait()
		for running in psutil.process_iter():
			if (running.create_time() >= NIEPTIME - 1):
				if ("python" in running.cmdline() and "Launcher.py" in running.cmdline()):
					NIEPPROCESS = running
					break
	except Exception as e:
		NIEPTIME = None
		NIEPPROCESS = None
		return "COULD NOT CREATE A NIEP INSTANCE", 405	

	return "SUCCESS", 200


def clean():

	shutil.rmtree("./PACKAGE")
	os.makedirs("./PACKAGE")

#########################################################################################################################################

############################################################## HTTP SERVER ##############################################################

@APP.route("/setup", methods=["POST"])
def setup():
	
	return up(flask.request.args)


@APP.route("/remote", methods=["POST"])
def remote():
	if len(flask.request.files) == 1 and "package" in flask.request.files:
	    uploaded_file = flask.request.files['package']
	    if uploaded_file.filename != '' and uploaded_file.filename.endswith(".zip"):
	    	uploaded_file.filename = "./PACKAGE/" + uploaded_file.filename
	        
	        clean()
	        uploaded_file.save(uploaded_file.filename)
	        
	        with zipfile.ZipFile(uploaded_file.filename, 'r') as zipped:
    			zipped.extractall("./PACKAGE/")

    		if not os.path.isfile(uploaded_file.filename[:-4] + "/Topology.json"):
    			return "INVALID PACKAGE STRUCTURE OR FILES", 405

    		return up({"path":uploaded_file.filename[:-4] + "/Topology.json"})
	    else:
	    	return "EMPTY OR INVALID FILE NAME SENT", 405
	else:
		return "INVALID REQUEST OR NO FILE SENT", 405
	
	return "SUCCESS", 200


@APP.route("/kill", methods=["POST"])
def kill():
	global NIEPPROCESS
	

	if NIEPPROCESS != None:
		try:		
			os.kill(NIEPPROCESS.pid, signal.SIGKILL)
		except:
			pass		
		NIEPPROCESS = None
		return "SUCCESS", 200

	return "COULD NOT KILL THE NIEP PROCESS", 405

#########################################################################################################################################
	
if __name__ == '__main__':

	if len(sys.argv) == 1:
		APP.run(debug=True)
	else:
		try:
			ipaddress.ip_address(unicode(sys.argv[1]))
		except Exception as e:
			print(e)
			print("INVALID IPV4 ADDRESS PROVIDED!")
			exit(1)
    	APP.run(debug=True, host=sys.argv[1])
