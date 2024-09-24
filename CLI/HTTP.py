import os
import time
import flask
import signal
import psutil
import os.path
import subprocess

NIEPPROCESS = None
NIEPTIME = None
APP = flask.Flask(__name__)

@APP.route("/setup", methods=["POST"])
def setup():
	global NIEPTIME
	global NIEPPROCESS

	if NIEPPROCESS != None:
		if not NIEPPROCESS.pid in [p.pid for p in psutil.process_iter()]:
			NIEPPROCESS = None
		else:
			return "NIEP ALREADY UP", 405	
	if not "path" in flask.request.args:
		return "NO FILE PATH PROVIDED!", 400
	if not os.path.isfile(flask.request.args["path"]):
		return "INVALID FILE PATH PROVIDED", 400

	try:	
		NIEPTIME = time.time()		
		NIEPPROCESS = subprocess.Popen(["gnome-terminal", "--", "python", "Launcher.py", flask.request.args["path"]])
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

	
if __name__ == '__main__':
	APP.run(debug=True)
