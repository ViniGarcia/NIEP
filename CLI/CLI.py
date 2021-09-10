from sys import path
from subprocess import call
from subprocess import STDOUT
from os import devnull, listdir
from os.path import isfile, abspath, commonprefix
from mininet.cli import CLI

import cmd
import readline
import rlcompleter

path.insert(0, '/'.join(abspath(__file__).split('/')[:-2] + ['TOPO-MAN']))
from Executer import Executer
from Parser import PlatformParser

#MISSING TASKS (priority order):
# 1.Distributed mode
# 2.VNF-REPO (HTTP, Local)
# 3.Assisted creation for SFCs and VNFs
# 4.See SFC structure
# 5.API Interface
# 6.PyCOO scripts
# 7.Graphical interface

#FNULL: redirects the system call normal output
FNULL = open(devnull, 'w')

#ERRORS: definition of errors for execution debug
PARSERERRORS = {-1: "Invalid definition file path or invalid key included",
                -2: "Invalid data type included as a key value",
                -3: "Invalid VNF configuration provided",
                -4: "Invalid SFC file path provided",
                -5: "Invalid SFC configuration provided",
                -6: "Invalid Mininet configuration provided",
                -7: "Invalid Mininet host configuration provided",
                -8: "Invalid Mininet switch configuration provided",
                -9: "Invalid Mininet controller configuration provided",
                -10: "Invalid Mininet OVS switch configuration provided",
                -11: "Invalid connections configuration provided",
                -12: "Invalid In/Out point configuration provided",
                -13: "Invalid Out/In point configuration provided",
                -14: "Inconsistent in In/Out and Out/In poits"}
EXECUTERERRORS = {-1: "Mininet network interfaces mapping failed",
                  -2: "Invalid definition of Mininet network interface",
                  -3: "Unrecognized Mininet network interface",
                  -4: "Parser error detected"}

def PATHCOMPLETER(line, text):

    line = line[:-len(text)]
    if line.endswith("\\ "):
        line = line.replace("\\ ", "\0")
        prefix = line.split(" ")[-1].replace("\0", " ")
        text = prefix + text
        prefix = prefix.replace(" ", "\\ ")
    else:
        prefix = ""

    try:    
        children_dir = listdir(text + "/")
        if len(children_dir) > 1:
            if not text.endswith("/"):
                readline.insert_text("/")
            return children_dir  + [".", ".."]
        if len(children_dir) == 1:
            if text.endswith("/"):
                return [(text.replace(" ", "\\ ") + children_dir[0].replace(" ", "\\ ")).replace(prefix, "")]
            else:
                return [(text.replace(" ", "\\ ") + "/" + children_dir[0].replace(" ", "\\ ")).replace(prefix, "")]
    except:
        pass

    last_dir = text.rfind("/")
    if last_dir != -1:
        children_dir = listdir(text[:last_dir] + "/")
        subpath_prefix = text[last_dir+1:]
        supaths_dir = [f for f in children_dir if f.startswith(subpath_prefix)]
        if len(supaths_dir) == 0:
            return []
        if len(supaths_dir) == 1:
            return [(text[:last_dir].replace(" ", "\\ ") + "/" + supaths_dir[0].replace(" ", "\\ ")).replace(prefix, "")]
        else:
            common_prefix = commonprefix(supaths_dir)
            if len(common_prefix) < 2 or len(common_prefix) <= len(text[last_dir+1:]):
                return supaths_dir + [".", ".."]
            else:
                return [(text[:last_dir].replace(" ", "\\ ") + "/" + common_prefix.replace(" ", "\\ ")).replace(prefix, "")]

    return []

class NIEPCLI(cmd.Cmd):

    prompt = 'niep> '
    NIEPEXE = None
    VMEXEC = None
    VNFEXEC = None
    SFCEXEC = None
    CLICOMP = None    

##################################################################################################################################
# NIEP INTERFACE

    def do_help(self, args):
        if self.prompt == 'niep> ':
            print '\n############### HELP #################'
            print '-> NIEP PROMPT <-'
            print '\tdefine path -> input a NIEP topology define in path argument'
            print '\ttopoup -> up a defined architecture'
            print '\ttopodown -> down an started architecture'
            print '\ttopoclean -> if an architecture defined and started, downs it and clean the definition'
            print '\ttopodestroy -> clean the definition and delete the topology NIEP files'
            print '\tvm arg -> assumes a VM or list the defined ones'
            print '\t\t-> arg = list (list every defined VM ID)'
            print '\t\t-> arg = VM ID (assumes VM ID prompt)'
            print '\tvnf arg -> assumes a VNF or list the defined ones'
            print '\t\t-> arg = list (list every defined VNF ID)'
            print '\t\t-> arg = VNF ID (assumes VNF ID prompt)'
            print '\tsfc arg -> assumes a SFC or list the defined ones'
            print '\t\t-> arg = list (list every defined SFC ID)'
            print '\t\t-> arg = SFC ID (assumes SFC ID prompt)'
            print '\tmininet -> assumes the mininet prompt\n'
            print '-> VM PROMPT <-'
            print '\tvmmanagement -> return the VM management interface address'
            print '\tvmssh arg1 arg2-> try to establish a ssh connection with the VM'
            print '\t\targ1 -> username'
            print '\t\targ2 -> password\n'
            print '-> VNF PROMPT <-'
            print '\tvnfmanagement -> return the VNF management interface address'
            print '\tvnfup -> wake the VNF'
            print '\tvnfdown -> sleep the VNF'
            print '\tvnfaction arg -> execute an action in the VNF instance or list possible actions'
            print '\t\t-> arg = list (list every possible action and them definitions)'
            print '\t\t-> arg = action (execute the requested action)'
            print '-> SFC PROMPT <-'
            print '\tsfcmanagement -> return the SFC\'s VNFS management interface addresses'
            print '\tsfcup -> wake the SFC\'s VNFS'
            print '\tsfcdown -> sleep the SFC\'s VNFS\n'
            print '-> MININET PROMPT <-'
            print '\tMininet legacy functions'
            print '######################################\n'
        else:
            print 'NIEP PROMPT COMMAND'
    
    def do_define(self, args):
        if self.prompt == 'niep> ':
            splited_args = args.split(' ')
            if not len(splited_args) == 1:
                print 'WRONG ARGUMENTS AMOUNT - 1 ARGUMENT EXPECTED'
                return

            NIEPPARSER = PlatformParser(args)
            if NIEPPARSER.STATUS != 0:
                print("ERROR: " + PARSERERRORS[NIEPPARSER.STATUS] + " (DEFINE / PARSER)")
                return

            self.NIEPEXE = Executer(NIEPPARSER)
            if not self.NIEPEXE.STATUS == None:
                print("ERROR: " + EXECUTERERRORS[self.NIEPEXE.STATUS] + " (DEFINE / EXECUTER)")
                self.NIEPEXE = None
                return
        else:
            print 'NIEP PROMPT COMMAND'

    def complete_define(self, text, line, begidx, endidx):
        
        return PATHCOMPLETER(line, text)

    def do_topoup(self, args):
        if self.prompt == 'niep> ':
            if not self.NIEPEXE == None: 
                splited_args = args.split(' ')
                if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                    print 'WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED'
                    return
                
                if self.NIEPEXE.STATUS != None:
                    print 'THIS COMMAND WAS ALREADY EXECUTED FOR THIS TOPOLOGY - CODE ' + str(self.NIEPEXE.STATUS)
                    return

                self.NIEPEXE.topologyUp()
                if not self.NIEPEXE.STATUS == 0:
                    print 'PROBLEMS ON TOPOLOGY DEFINITION ON UP PROCESS - TOPOLOGY UNDEFINED (' + str(self.NIEPEXE.STATUS) + ')'
                    self.NIEPEXE = None
                    return
            else:
                print 'NO TOPOLOGY DEFINED'
        else:
            print 'NIEP PROMPT COMMAND'

    def do_topodown(self, args):
        if self.prompt == 'niep> ':
            if not self.NIEPEXE == None: 
                splited_args = args.split(' ')
                if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                    print 'WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED'
                    return

                self.NIEPEXE.topologyDown()
                if not self.NIEPEXE.STATUS == None:
                    print 'PROBLEMS ON TOPOLOGY DEFINITION ON DOWN PROCESS - TOPOLOGY UNDEFINED (' + str(self.NIEPEXE.STATUS) + ')'
                    self.NIEPEXE = None
                    return
            else:
                print 'NO TOPOLOGY DEFINED'
        else:
            print 'NIEP PROMPT COMMAND'

    def do_topoclean(self, args):
        if self.prompt == 'niep> ':
            splited_args = args.split(' ')
            if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                print 'WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED'
                return

            if not self.NIEPEXE == None: 
                if self.NIEPEXE.STATUS == 0:
                    self.NIEPEXE.topologyDown()
                self.VMEXEC = None
                self.VNFEXEC = None
                self.SFCEXEC = None
                del self.NIEPEXE
            else:
                print 'NO TOPOLOGY DEFINED'
        else:
            print 'NIEP PROMPT COMMAND' 

    def do_topodestroy(self, args):
        if self.prompt == 'niep> ':
            splited_args = args.split(' ')
            if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                print 'WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED'
                return

            if not self.NIEPEXE == None:
                if self.NIEPEXE.STATUS == 0:
                    self.NIEPEXE.topologyDown() 
                for VNFINSTANCE in self.NIEPEXE.VNFS:
                    call(['rm', '-r', '../VEM/IMAGES/' + self.NIEPEXE.VNFS[VNFINSTANCE].ID], stdout=FNULL, stderr=STDOUT)
                for VMINSTANCE in self.NIEPEXE.VMS:
                    call(['rm', '-r', '../VEM/IMAGES/' + self.NIEPEXE.VMS[VMINSTANCE].ID], stdout=FNULL, stderr=STDOUT)
                self.VMEXEC = None
                self.VNFEXEC = None
                self.SFCEXEC = None
                del self.NIEPEXE
            else:
                 print 'NO TOPOLOGY DEFINED'
        else:
            print 'NIEP PROMPT COMMAND'  

    def do_vm(self, args):
        if self.prompt == 'niep> ':
            if not self.NIEPEXE == None:
                if not self.NIEPEXE.STATUS == 0:
                    print 'TOPOLOGY IS NOT UP'
                    return

                splited_args = args.split(' ')
                if not len(splited_args) == 1:
                    print 'WRONG ARGUMENTS AMOUNT - 1 ARGUMENT EXPECTED'
                    return

                if args == 'list':
                    print '\n############## VMS LIST ###############'
                    for VM in self.NIEPEXE.VMS:
                        print(VM)
                    print '#######################################\n'
                    return

                if args in self.NIEPEXE.VMS:
                    self.changecontext(self.prompt, "vm")
                    self.VMEXEC = self.NIEPEXE.VMS[args]
                    self.prompt = 'vm(' + args + ')> '
                    return
                else:
                    print 'VM ' + args + ' NOT FOUND'
            else:
                print 'NO TOPOLOGY DEFINED'
        else:
            print 'NIEP PROMPT COMMAND'

    def complete_vm(self, text, line, begidx, endidx):

        if self.NIEPEXE == None or self.NIEPEXE.STATUS != 0:
            return []

        if self.NIEPEXE.VMS == None or len(self.NIEPEXE.VMS) == 0:
            return ['list']

        args_list = ['list'] + list(self.NIEPEXE.VMS.keys())
        if len(text) == 0:
            return args_list
        args_sublist = [a for a in args_list if a.startswith(text)]
        if len(args_sublist) == 0:
            return []
        if len(args_sublist) == 1:
            return args_sublist
        else:
            common_prefix = commonprefix(args_sublist)
            if len(common_prefix) < 2 or len(common_prefix) <= len(text):
                return args_sublist
            else:
                return [common_prefix]

        return []

    def do_vnf(self, args):
        if self.prompt == 'niep> ':
            if not self.NIEPEXE == None:
                if not self.NIEPEXE.STATUS == 0:
                    print 'TOPOLOGY IS NOT UP'
                    return

                splited_args = args.split(' ')
                if not len(splited_args) == 1:
                    print 'WRONG ARGUMENTS AMOUNT - 1 ARGUMENT EXPECTED'
                    return
                
                if args == 'list':
                    print '\n############## VNFS LIST ##############'
                    for VNF in self.NIEPEXE.VNFS:
                        print VNF
                    print '#######################################\n'
                    return

                if args in self.NIEPEXE.VNFS:
                    self.changecontext(self.prompt, "vnf")
                    self.VNFEXEC = self.NIEPEXE.VNFS[args]
                    self.prompt = 'vnf(' + args + ')> '
                    return
                else:
                     print 'VNF ' + args + ' NOT FOUND'
            else:
                print 'NO TOPOLOGY DEFINED'
        else:
            print 'NIEP PROMPT COMMAND'

    def complete_vnf(self, text, line, begidx, endidx):

        if self.NIEPEXE == None or self.NIEPEXE.STATUS != 0:
            return []

        if self.NIEPEXE.VNFS == None or len(self.NIEPEXE.VNFS) == 0:
            return ['list']

        args_list = ['list'] + list(self.NIEPEXE.VNFS.keys())
        if len(text) == 0:
            return args_list
        args_sublist = [a for a in args_list if a.startswith(text)]
        if len(args_sublist) == 0:
            return []
        if len(args_sublist) == 1:
            return args_sublist
        else:
            common_prefix = commonprefix(args_sublist)
            if len(common_prefix) < 2 or len(common_prefix) <= len(text):
                return args_sublist
            else:
                return [common_prefix]

        return []

    def do_sfc(self, args):
        if self.prompt == 'niep> ':
            if not self.NIEPEXE == None:
                if not self.NIEPEXE.STATUS == 0:
                    print 'TOPOLOGY IS NOT UP'
                    return

                splited_args = args.split(' ')
                if not len(splited_args) == 1:
                    print 'WRONG ARGUMENTS AMOUNT - 1 ARGUMENT EXPECTED'
                    return
                
                if args == 'list':
                    print '\n############## SFCS LIST ##############'
                    for SFC in self.NIEPEXE.CONFIGURATION.SFCS:
                        print SFC.ID
                    print '#######################################\n'
                    return

                for SFC in self.NIEPEXE.CONFIGURATION.SFCS:
                    if args == SFC.ID:
                        self.changecontext(self.prompt, "sfc")
                        self.SFCEXEC = SFC
                        self.prompt = 'sfc(' + args + ')> ' 
                        return
                print 'SFC ' + args + ' NOT FOUND'
            else:
                print 'NO TOPOLOGY DEFINED'
        else:
            print 'NIEP PROMPT COMMAND'

    def complete_sfc(self, text, line, begidx, endidx):

        if self.NIEPEXE == None or self.NIEPEXE.STATUS != 0:
            return []

        if self.NIEPEXE.CONFIGURATION.SFCS == None or len(self.NIEPEXE.VNFS) == 0:
            return ['list']

        args_list = ['list'] + [sfc.ID for sfc in self.NIEPEXE.CONFIGURATION.SFCS]
        if len(text) == 0:
            return args_list
        args_sublist = [a for a in args_list if a.startswith(text)]
        if len(args_sublist) == 0:
            return []
        if len(args_sublist) == 1:
            return args_sublist
        else:
            common_prefix = commonprefix(args_sublist)
            if len(common_prefix) < 2 or len(common_prefix) <= len(text):
                return args_sublist
            else:
                return [common_prefix]

        return []

    def do_mininet(self, args):
        if self.prompt == 'niep> ':
            if not self.NIEPEXE == None:
                if not self.NIEPEXE.STATUS == 0:
                    print 'TOPOLOGY IS NOT UP'
                    return

                splited_args = args.split(' ')
                if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                    print 'WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED'
                    return

                CLI(self.NIEPEXE.NET)
            else:
                print 'NO TOPOLOGY DEFINED'
        else:
            print 'NIEP PROMPT COMMAND'

##################################################################################################################################

##################################################################################################################################
# VM INTERFACE

    def do_vmmanagement(self, args):
        if self.prompt.startswith('vm'):
            splited_args = args.split(' ')
            if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                print 'WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED'
                return

            management = self.VMEXEC.managementVM()
            if management == None:
                print 'INVALID VM STATUS'
                return
            if management == -1:
                print 'VM IS NOT UP'
                return
            if management == -2:
                print 'ARP PROBLEMS'
                return
            else:
                print management
        else:
            print 'VM PROMPT COMMAND'

    def do_vmssh(self, args):
        if self.prompt.startswith('vm'):
            splited_args = args.split(' ')
            if len(splited_args) != 2:
                print 'WRONG ARGUMENTS AMOUNT - 2 ARGUMENTS EXPECTED'
                return
            self.VMEXEC.sshVM(splited_args[0], splited_args[1])
        else:
            print 'VM PROMPT COMMAND'

##################################################################################################################################

##################################################################################################################################
# VNFS INTERFACE

    def do_vnfmanagement(self, args):
        if self.prompt.startswith('vnf'):
            splited_args = args.split(' ')
            if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                print 'WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED'
                return

            management = self.VNFEXEC.managementVNF()
            if management == None:
                print 'INVALID VNF STATUS'
                return
            if management == -1:
                print 'VNF IS NOT UP'
                return
            if management == -2:
                print 'ARP PROBLEMS'
                return
            else:
                print management
        else:
            print 'VNF PROMPT COMMAND'

    def do_vnfup(self, args):
        if self.prompt.startswith('vnf'):
            splited_args = args.split(' ')
            if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                print 'WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED'
                return

            upstatus = self.VNFEXEC.upVNF()
            if upstatus == None:
                print 'INVALID VNF STATUS'
                return
            if upstatus == -2:
                print 'VNF DOES NOT EXIST'
                return
            if upstatus == -1:
                print 'VNF ALREADY UP'
                return
        else:
            print 'VNF PROMPT COMMAND'

    def do_vnfdown(self, args):
        if self.prompt.startswith('vnf'):
            splited_args = args.split(' ')
            if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                print 'WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED'
                return

            downstatus = self.VNFEXEC.sleepVNF()
            if downstatus == None:
                print 'INVALID VNF STATUS'
                return
            if downstatus == -2:
                print 'VNF DOES NOT EXIST'
                return
            if downstatus == -1:
                print 'VNF ALREADY DOWN'
                return
        else:
            print 'VNF PROMPT COMMAND'

    def do_vnfaction(self, args):
        if self.prompt.startswith('vnf'):
            splited_args = args.split(' ')
            if len(splited_args) > 2 or len(splited_args) == 1 and len(splited_args[0]) == 0:
                print 'WRONG ARGUMENTS AMOUNT - 1 OR 2 ARGUMENTS EXPECTED'
                return

            actionstatus = None
            if len(splited_args) == 1:
                if args == 'list':
                    print '\n############# ACTION LIST #############'
                    print 'start -> start the VNF function'
                    print 'stop -> stop the VNF function' 
                    print 'replace path -> replace the function with the function in path'
                    print 'running -> check if VNF is running'
                    print 'data -> check the VNF function'
                    print 'id -> check the VNF ID'
                    print 'metrics -> check the VNF metrics'
                    print 'log -> check the VNF log'
                    print '#######################################\n'
                    return
                if args == 'start':
                    actionstatus = self.VNFEXEC.controlVNF('function_start', [])
                else:
                    if args == 'stop':
                        actionstatus = self.VNFEXEC.controlVNF('function_stop', [])
                    else:
                        if args == 'running':
                            actionstatus = self.VNFEXEC.controlVNF('function_run', [])
                        else:
                            if args == 'data':
                                actionstatus = self.VNFEXEC.controlVNF('function_data', [])
                            else:
                                if args == 'id':
                                    actionstatus = self.VNFEXEC.controlVNF('function_id', [])
                                else:
                                    if args == 'metrics':
                                        actionstatus = self.VNFEXEC.controlVNF('function_metrics', [])
                                    else:
                                        if args == 'log':
                                            actionstatus = self.VNFEXEC.controlVNF('function_log', [])
            if len(splited_args) == 2:
                if splited_args[0] == 'replace':
                    actionstatus = self.VNFEXEC.controlVNF('function_replace', [splited_args[1]])

            if actionstatus == None:
                print 'UNDEFINED ACTION'
                return
            if actionstatus == -1:
                print 'VNF IS NOT UP'
                return
            if actionstatus == -2:
                print 'VNF MANAGEMENT IS NOT ACCESIBLE'
                return
            if actionstatus == -3:
                print 'FILE DOES NOT EXISTS'
                return
            if type(actionstatus) is list:
                if actionstatus[0] == '200':
                    print actionstatus[1]
                else:
                    print 'REST ERROR - ' + str(actionstatus[0])
                return
            if not actionstatus == 200:
                print 'REST ERROR - ' + str(actionstatus)

        else:
            print 'VNF PROMPT COMMAND'

    def complete_vnfaction(self, text, line, begidx, endidx):

        args_list = ['list', 'start', 'stop', 'replace', 'runnig', 'data', 'id', 'metrics', 'log']
        line_arg = line.split(' ')

        if len(line_arg) == 2:
            if len(text) == 0:
                return args_list
            args_sublist = [a for a in args_list if a.startswith(text)]
            if len(args_sublist) == 0:
                return []
            if len(args_sublist) == 1:
                return args_sublist
            else:
                common_prefix = commonprefix(args_sublist)
                if len(common_prefix) < 2 or len(common_prefix) <= len(text):
                    return args_sublist
                else:
                    return [common_prefix]
        elif len(line_arg) == 3:
            if line_arg[1] == 'replace':
                return PATHCOMPLETER(line, text)

        return []

##################################################################################################################################

##################################################################################################################################
# SFCS INTERFACE
    
    def do_sfcmanagement(self, args):
        if self.prompt.startswith('sfc'):
            splited_args = args.split(' ')
            if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                print 'WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED'
                return

            if not self.SFCEXEC.checkStatusSFC():
                print 'SFC IS NOT UP OR NOT TOTALLY UP'
                return

            management = self.SFCEXEC.managementSFC()
            if management == None:
                print 'INVALID SFC STATUS'
                return
            if management == -1:
                print 'SFC IS NOT UP'
                return
            if management == -2:
                print 'ARP PROBLEMS'
                return
            else:
                for managementData in management:
                    print managementData
        else:
            print 'SFC PROMPT COMMAND'

    def do_sfcup(self, args):
        if self.prompt.startswith('sfc'):
            splited_args = args.split(' ')
            if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                print 'WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED'
                return

            self.SFCEXEC.checkStatusSFC()
            upstatus = self.SFCEXEC.wakeSFC()
            if upstatus == None:
                print 'INVALID SFC STATUS'
                return
            if upstatus == -1:
                print 'SFC ALREADY UP'
                return
        else:
            print 'SFC PROMPT COMMAND'

    def do_sfcdown(self, args):
        if self.prompt.startswith('sfc'):
            splited_args = args.split(' ')
            if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                print 'WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED'
                return

            self.SFCEXEC.checkStatusSFC()
            downstatus = self.SFCEXEC.sleepSFC()
            if downstatus == None:
                print 'INVALID SFC STATUS'
                return
            if downstatus == -1:
                print 'SFC ALREADY DOWN'
                return
        else:
            print 'SFC PROMPT COMMAND'

##################################################################################################################################

##################################################################################################################################
# GLOBAL CALL FOR CLI

    def do_exit(self, args):
        if not self.prompt == 'niep> ':
            self.changecontext(self.prompt, "niep")
            self.prompt = 'niep> '
            return

        if not self.NIEPEXE == None:
            if self.NIEPEXE.STATUS == 0:
                self.NIEPEXE.topologyDown()

        return True

    def do_EOF(self, args):
        return True
    
    def preloop(self):
        try:
            if 'libedit' in readline.__doc__:
                readline.parse_and_bind("bind ^I rl_complete")
            else:
                readline.parse_and_bind("tab: complete")
            readline.set_completer_delims(readline.get_completer_delims().replace('/', ''))
            readline.set_history_length(100)
            readline.read_history_file(abspath(__file__)[:abspath(__file__).rindex("/")] + "/CLIMEM/NIEPMEM")
            return True
        except Exception as e:
            return False

    def postloop(self):
        try:
            if self.prompt.startswith("niep"):
                readline.write_history_file(abspath(__file__)[:abspath(__file__).rindex("/")] + "/CLIMEM/NIEPMEM")
            elif self.prompt.startswith("vm"):
                readline.write_history_file(abspath(__file__)[:abspath(__file__).rindex("/")] + "/CLIMEM/VMMEM")   
            elif self.prompt.startswith("vnf"):
                readline.write_history_file(abspath(__file__)[:abspath(__file__).rindex("/")] + "/CLIMEM/VNFMEM")
            elif self.prompt.startswith("sfc"):
                readline.write_history_file(abspath(__file__)[:abspath(__file__).rindex("/")] + "/CLIMEM/SFCMEM")
            return True
        except Exception as e:
            return False

    def changecontext(self, current, succeeding):
        try:
            if current.startswith("niep"):
                readline.write_history_file(abspath(__file__)[:abspath(__file__).rindex("/")] + "/CLIMEM/NIEPMEM")
            elif current.startswith("vm"):
                readline.write_history_file(abspath(__file__)[:abspath(__file__).rindex("/")] + "/CLIMEM/VMMEM")
            elif current.startswith("vnf"):
                readline.write_history_file(abspath(__file__)[:abspath(__file__).rindex("/")] + "/CLIMEM/VNFMEM")
            elif current.startswith("sfc"):
                readline.write_history_file(abspath(__file__)[:abspath(__file__).rindex("/")] + "/CLIMEM/SFCMEM")
            

            readline.clear_history()

            if succeeding.startswith("niep"):
                readline.read_history_file(abspath(__file__)[:abspath(__file__).rindex("/")] + "/CLIMEM/NIEPMEM")
            elif succeeding.startswith("vm"):
                readline.read_history_file(abspath(__file__)[:abspath(__file__).rindex("/")] + "/CLIMEM/VMMEM")
            elif succeeding.startswith("vnf"):
                readline.read_history_file(abspath(__file__)[:abspath(__file__).rindex("/")] + "/CLIMEM/VNFMEM")
            elif succeeding.startswith("sfc"):
                readline.read_history_file(abspath(__file__)[:abspath(__file__).rindex("/")] + "/CLIMEM/SFCMEM")

            return True
        except Exception as e:
            return False

##################################################################################################################################

if __name__ == '__main__':

    print("\n===========================================")
    print("==== _____   _________________________  ===") 
    print("==== ___  | / /___  _/__  ____/__  __ \\ ===")
    print("==== __   |/ / __  / __  __/  __  /_/ / ===")
    print("==== _  /|  / __/ /  _  /___  _  ____/  ===")
    print("==== /_/ |_/  /___/  /_____/  /_/       ===")
    print("===========================================")
    print("== NFV Infrastructure Emulation Platform ==")
    print("===========================================\n")  

    NIEPCLI().cmdloop()