from cmd import Cmd
from sys import path
from subprocess import call
from subprocess import STDOUT
from os import devnull
from os.path import isfile, abspath
from mininet.cli import CLI
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

class NIEPCLI(Cmd):

    prompt = 'niep> '
    NIEPEXE = None
    VNFEXEC = None
    SFCEXEC = None

##################################################################################################################################
# NIEP INTERFACE

    def do_help(self, args):
        if self.prompt == 'niep> ':
            print '\n############### HELP #################'
            print '-> NIEP PROMPT <-'
            print '\tdefine path -> input a NIEP topology define in path argument'
            print '\ttopoup -> up a defined architecture'
            print '\ttopodown -> down an upped architecture'
            print '\ttopoclean -> if an architecture defined and upped, downs it and clean the definition'
            print '\ttopodestroy -> clean the definition and delete the topology NIEP files'
            print '\tvnf arg -> assumes a VNF or list the defined ones'
            print '\t\t-> arg = list (list every defined VNF ID)'
            print '\t\t-> ard = VNF ID (assumes VNF ID prompt)'
            print '\tsfc arg -> assumes a SFC or list the defined ones'
            print '\t\t-> arg = list (list every defined SFC ID)'
            print '\t\t-> ard = SFC ID (assumes SFC ID prompt)'
            print '\tmininet -> assumes the mininet prompt\n'
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
                    self.NIEPEXE = None
                    print 'PROBLEMS ON TOPOLOGY DEFINITION ON UP PROCESS - TOPOLOGY UNDEFINED'
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
                    self.NIEPEXE = None
                    print 'PROBLEMS ON TOPOLOGY DEFINITION ON DOWN PROCESS - TOPOLOGY UNDEFINED'
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
                self.VNFEXEC = None
                self.SFCEXEC = None
                del self.NIEPEXE
            else:
                 print 'NO TOPOLOGY DEFINED'
        else:
            print 'NIEP PROMPT COMMAND'  

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
                    self.VNFEXEC = self.NIEPEXE.VNFS[args]
                    self.prompt = 'vnf(' + args + ')> '
                    return
                else:
                     print 'VNF ' + args + ' NOT FOUND'
            else:
                print 'NO TOPOLOGY DEFINED'
        else:
            print 'NIEP PROMPT COMMAND'

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
                        self.SFCEXEC = SFC
                        self.prompt = 'sfc(' + args + ')> ' 
                        return
                print 'SFC ' + args + ' NOT FOUND'
            else:
                print 'NO TOPOLOGY DEFINED'
        else:
            print 'NIEP PROMPT COMMAND'

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
            self.prompt = 'niep> '
            return

        if not self.NIEPEXE == None:
            if self.NIEPEXE.STATUS == 0:
                self.NIEPEXE.topologyDown()

        exit()

    def do_EOF(self, args):
        return True
    
    def postloop(self):
        print ''
        return True

##################################################################################################################################

if __name__ == '__main__':
    NIEPCLI().cmdloop()

# /home/gt-fende/Documentos/NIEP/EXAMPLES/DEFINITIONS/VNFExample.json
# /home/gt-fende/Documentos/NIEP/EXAMPLES/DEFINITIONS/SFCExample.json
# /home/gt-fende/Documentos/NIEP/VNF-REPO/firewall.click