from sys import path
from os import listdir
from os.path import abspath, commonprefix
from mininet.cli import CLI

import cmd
import readline
import rlcompleter

path.insert(0, '/'.join(abspath(__file__).split('/')[:-2] + ['TOPO-MAN']))
from Service import TopologyService, VMService, VNFService, SFCService

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

    def __init__(self):
        super().__init__()
        self.prompt = 'niep> '
        self.NIEPEXE = None
        self.VMEXEC = None
        self.VNFEXEC = None
        self.SFCEXEC = None
        self.CLICOMP = None
        self.TOPOLOGY = TopologyService()
        self.VMSERVICE = VMService(self.TOPOLOGY)
        self.VNFSERVICE = VNFService(self.TOPOLOGY)
        self.SFCSERVICE = SFCService(self.TOPOLOGY)

    def sync_executor(self):
        self.NIEPEXE = self.TOPOLOGY.executor

##################################################################################################################################
# NIEP INTERFACE

    def do_help(self, args):
        if self.prompt == 'niep> ':
            print('\n############### HELP #################')
            print('-> NIEP PROMPT <-')
            print('\tdefine path -> input a NIEP topology define in path argument')
            print('\ttopoup -> up a defined architecture')
            print('\ttopodown -> down an started architecture')
            print('\ttopoclean -> if an architecture defined and started, downs it and clean the definition')
            print('\ttopodestroy -> clean the definition and delete the topology NIEP files')
            print('\tvm arg -> assumes a VM or list the defined ones')
            print('\t\t-> arg = list (list every defined VM ID)')
            print('\t\t-> arg = VM ID (assumes VM ID prompt)')
            print('\tvnf arg -> assumes a VNF or list the defined ones')
            print('\t\t-> arg = list (list every defined VNF ID)')
            print('\t\t-> arg = VNF ID (assumes VNF ID prompt)')
            print('\tsfc arg -> assumes a SFC or list the defined ones')
            print('\t\t-> arg = list (list every defined SFC ID)')
            print('\t\t-> arg = SFC ID (assumes SFC ID prompt)')
            print('\tmininet -> assumes the mininet prompt\n')
            print('-> VM PROMPT <-')
            print('\tvmmanagement -> return the VM management interface address')
            print('\tvmssh arg1 arg2-> try to establish a ssh connection with the VM')
            print('\t\t-> arg1 -> username')
            print('\t\t-> arg2 -> password\n')
            print('-> VNF PROMPT <-')
            print('\tvnfmanagement -> return the VNF management interface address')
            print('\tvnfup -> wake the VNF')
            print('\tvnfdown -> sleep the VNF')
            print('\tvnfaction arg -> execute an action in the VNF instance or list possible actions')
            print('\t\t-> arg = list (list every possible action and them definitions)')
            print('\t\t-> arg = action (execute the requested action)')
            print('\tvnfscript arg1 arg2 -> execute a set of actions provided in a script file')
            print('\t\targ1 = main scipt file path')
            print('\t\targ2 = error recover script file path (optional)')
            print('-> SFC PROMPT <-')
            print('\tsfcmanagement -> return the SFC\'s VNFS management interface addresses')
            print('\tsfcup -> wake the SFC\'s VNFS')
            print('\tsfcdown -> sleep the SFC\'s VNFS\n')
            print('-> MININET PROMPT <-')
            print('\tMininet legacy functions')
            print('######################################\n')
        else:
            print('NIEP PROMPT COMMAND')
    
    def do_define(self, args):
        if self.prompt == 'niep> ':
            splited_args = args.split(' ')
            if not len(splited_args) == 1:
                print('WRONG ARGUMENTS AMOUNT - 1 ARGUMENT EXPECTED')
                return

            result = self.TOPOLOGY.define(args)
            self.sync_executor()
            if not result.ok:
                if result.code == "parser_error":
                    print("ERROR: " + result.message + " (DEFINE / PARSER / " + str(result.status) + ")")
                    if result.detail:
                        print("DETAIL: " + result.detail)
                else:
                    print("ERROR: " + result.message + " (DEFINE / EXECUTER /" + str(result.status) + ")")
                return
        else:
            print('NIEP PROMPT COMMAND')

    def complete_define(self, text, line, begidx, endidx):
        
        return PATHCOMPLETER(line, text)

    def do_topoup(self, args):
        if self.prompt == 'niep> ':
            if not self.NIEPEXE == None:
                splited_args = args.split(' ')
                if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                    print('WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED')
                    return

                result = self.TOPOLOGY.up()
                self.sync_executor()
                if result.code == "already_executed":
                    print(result.message + ' - CODE ' + str(result.status))
                    return
                if not result.ok:
                    print(result.message + ' (' + str(result.status) + ')')
                    return
            else:
                print('NO TOPOLOGY DEFINED')
        else:
            print('NIEP PROMPT COMMAND')

    def do_topodown(self, args):
        if self.prompt == 'niep> ':
            if not self.NIEPEXE == None:
                splited_args = args.split(' ')
                if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                    print('WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED')
                    return

                result = self.TOPOLOGY.down()
                self.sync_executor()
                if not result.ok:
                    print(result.message + ' (' + str(result.status) + ')')
                    return
            else:
                print('NO TOPOLOGY DEFINED')
        else:
            print('NIEP PROMPT COMMAND')

    def do_topoclean(self, args):
        if self.prompt == 'niep> ':
            splited_args = args.split(' ')
            if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                print('WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED')
                return

            if not self.NIEPEXE == None:
                self.TOPOLOGY.clean()
                self.VMEXEC = None
                self.VNFEXEC = None
                self.SFCEXEC = None
                self.sync_executor()
            else:
                print('NO TOPOLOGY DEFINED')
        else:
            print('NIEP PROMPT COMMAND' )

    def do_topodestroy(self, args):
        if self.prompt == 'niep> ':
            splited_args = args.split(' ')
            if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                print('WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED')
                return

            if not self.NIEPEXE == None:
                self.TOPOLOGY.destroy()
                self.VMEXEC = None
                self.VNFEXEC = None
                self.SFCEXEC = None
                self.sync_executor()
            else:
                 print('NO TOPOLOGY DEFINED')
        else:
            print('NIEP PROMPT COMMAND'  )

    def do_vm(self, args):
        if self.prompt == 'niep> ':
            if not self.NIEPEXE == None:
                if not self.NIEPEXE.STATUS == 0:
                    print('TOPOLOGY IS NOT UP')
                    return

                splited_args = args.split(' ')
                if not len(splited_args) == 1:
                    print('WRONG ARGUMENTS AMOUNT - 1 ARGUMENT EXPECTED')
                    return

                if args == 'list':
                    print('\n############## VMS LIST ###############')
                    for VM in self.TOPOLOGY.vm_ids():
                        print(VM)
                    print('#######################################\n')
                    return

                if args in self.TOPOLOGY.vm_ids():
                    self.changecontext(self.prompt, "vm")
                    self.VMEXEC = self.TOPOLOGY.get_vm(args)
                    self.prompt = 'vm(' + args + ')> '
                    return
                else:
                    print('VM ' + args + ' NOT FOUND')
            else:
                print('NO TOPOLOGY DEFINED')
        else:
            print('NIEP PROMPT COMMAND')

    def complete_vm(self, text, line, begidx, endidx):

        if self.NIEPEXE == None or self.NIEPEXE.STATUS != 0:
            return []

        if len(self.TOPOLOGY.vm_ids()) == 0:
            return ['list']

        args_list = ['list'] + self.TOPOLOGY.vm_ids()
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
                    print('TOPOLOGY IS NOT UP')
                    return

                splited_args = args.split(' ')
                if not len(splited_args) == 1:
                    print('WRONG ARGUMENTS AMOUNT - 1 ARGUMENT EXPECTED')
                    return
                
                if args == 'list':
                    print('\n############## VNFS LIST ##############')
                    for VNF in self.TOPOLOGY.vnf_ids():
                        print(VNF)
                    print('#######################################\n')
                    return

                if args in self.TOPOLOGY.vnf_ids():
                    self.changecontext(self.prompt, "vnf")
                    self.VNFEXEC = self.TOPOLOGY.get_vnf(args)
                    self.prompt = 'vnf(' + args + ')> '
                    return
                else:
                     print('VNF ' + args + ' NOT FOUND')
            else:
                print('NO TOPOLOGY DEFINED')
        else:
            print('NIEP PROMPT COMMAND')

    def complete_vnf(self, text, line, begidx, endidx):

        if self.NIEPEXE == None or self.NIEPEXE.STATUS != 0:
            return []

        if len(self.TOPOLOGY.vnf_ids()) == 0:
            return ['list']

        args_list = ['list'] + self.TOPOLOGY.vnf_ids()
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
                    print('TOPOLOGY IS NOT UP')
                    return

                splited_args = args.split(' ')
                if not len(splited_args) == 1:
                    print('WRONG ARGUMENTS AMOUNT - 1 ARGUMENT EXPECTED')
                    return
                
                if args == 'list':
                    print('\n############## SFCS LIST ##############')
                    for SFC in self.TOPOLOGY.sfc_ids():
                        print(SFC)
                    print('#######################################\n')
                    return

                sfc = self.TOPOLOGY.get_sfc(args)
                if sfc is not None:
                    self.changecontext(self.prompt, "sfc")
                    self.SFCEXEC = sfc
                    self.prompt = 'sfc(' + args + ')> '
                    return
                print('SFC ' + args + ' NOT FOUND')
            else:
                print('NO TOPOLOGY DEFINED')
        else:
            print('NIEP PROMPT COMMAND')

    def complete_sfc(self, text, line, begidx, endidx):

        if self.NIEPEXE == None or self.NIEPEXE.STATUS != 0:
            return []

        if len(self.TOPOLOGY.sfc_ids()) == 0:
            return ['list']

        args_list = ['list'] + self.TOPOLOGY.sfc_ids()
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
                    print('TOPOLOGY IS NOT UP')
                    return

                splited_args = args.split(' ')
                if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                    print('WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED')
                    return

                CLI(self.NIEPEXE.NET)
            else:
                print('NO TOPOLOGY DEFINED')
        else:
            print('NIEP PROMPT COMMAND')

##################################################################################################################################

##################################################################################################################################
# VM INTERFACE

    def do_vmmanagement(self, args):
        if self.prompt.startswith('vm'):
            splited_args = args.split(' ')
            if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                print('WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED')
                return

            result = self.VMSERVICE.management(self.VMEXEC.ID)
            if not result.ok:
                print(result.message)
                return
            print(result.data)
        else:
            print('VM PROMPT COMMAND')

    def do_vmssh(self, args):
        if self.prompt.startswith('vm'):
            splited_args = args.split(' ')
            if len(splited_args) != 2:
                print('WRONG ARGUMENTS AMOUNT - 2 ARGUMENTS EXPECTED')
                return
            self.VMSERVICE.ssh(self.VMEXEC.ID, splited_args[0], splited_args[1])
        else:
            print('VM PROMPT COMMAND')

##################################################################################################################################

##################################################################################################################################
# VNFS INTERFACE

    def do_vnfmanagement(self, args):
        if self.prompt.startswith('vnf'):
            splited_args = args.split(' ')
            if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                print('WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED')
                return

            result = self.VNFSERVICE.management(self.VNFEXEC.ID)
            if not result.ok:
                print(result.message)
                return
            print(result.data)
        else:
            print('VNF PROMPT COMMAND')

    def do_vnfup(self, args):
        if self.prompt.startswith('vnf'):
            splited_args = args.split(' ')
            if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                print('WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED')
                return

            result = self.VNFSERVICE.up(self.VNFEXEC.ID)
            if not result.ok:
                if result.code == "invalid_vnf_status" and isinstance(result.data, dict):
                    print('INVALID VNF STATUS (VNF_STATUS=' + str(result.data.get('VNF_STATUS')) + ', VM_STATUS=' + str(result.data.get('VM_STATUS')) + ')')
                else:
                    print(result.message)
                return
        else:
            print('VNF PROMPT COMMAND')

    def do_vnfdown(self, args):
        if self.prompt.startswith('vnf'):
            splited_args = args.split(' ')
            if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                print('WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED')
                return

            result = self.VNFSERVICE.down(self.VNFEXEC.ID)
            if not result.ok:
                print(result.message)
                return
        else:
            print('VNF PROMPT COMMAND')

    def do_vnfaction(self, args):
        if self.prompt.startswith('vnf'):
            splited_args = args.split(' ')
            if len(splited_args) > 2 or len(splited_args) == 1 and len(splited_args[0]) == 0:
                print('WRONG ARGUMENTS AMOUNT - 1 OR 2 ARGUMENTS EXPECTED')
                return

            actionstatus = None
            if len(splited_args) > 0:
                result = self.VNFSERVICE.action(self.VNFEXEC.ID, splited_args[0], splited_args[1:])
                actionstatus = result.data if result.ok else result

            if hasattr(actionstatus, 'ok') and not actionstatus.ok:
                print(actionstatus.message)
                return

            if splited_args[0] == 'list':
                    print('\n############# ACTION LIST #############')
                    actionkeys = list(actionstatus.keys())
                    actionkeys.sort()
                    for action in actionkeys:
                        print(action + " -> " + actionstatus[action])
                    print('#######################################\n')
                    return

            if actionstatus[0]:
                if len(actionstatus) > 1:
                    print('SUCCESS [' + str(actionstatus[1]) + ']')
                else:
                    print('SUCCESS')
            else:
                if len(actionstatus) > 1:
                    print('VNF PLATFORM ERROR [' + str(actionstatus[1]) + ']')
                else:
                    print('VNF PLATFORM ERROR')

        else:
            print('VNF PROMPT COMMAND')

    def complete_vnfaction(self, text, line, begidx, endidx):

        args_list = list(self.VNFEXEC.controlVNF("list", []).keys())
        args_list.sort()

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
        elif len(line_arg) > 2:
            return PATHCOMPLETER(line, text)

        return []

    def do_vnfscript(self, args):
        if self.prompt.startswith('vnf'):
            
            splited_args = args.split(' ')
            if len(splited_args) > 2 or len(splited_args) == 1 and len(splited_args[0]) == 0:
                print('WRONG ARGUMENTS AMOUNT - 1 OR 2 ARGUMENTS EXPECTED')
                return

            if len(splited_args) == 1:
                result = self.VNFSERVICE.script(self.VNFEXEC.ID, splited_args[0], None)
            else:
                result = self.VNFSERVICE.script(self.VNFEXEC.ID, splited_args[0], splited_args[1])

            if not result.ok:
                print(result.message)
                return
            script_result = result.data

            print('\n############# EXECUTION SUMMARY #############')
            if not script_result[0] or len(script_result[1]) == 2:
                print('-> NORMAL SCRIPT (FAILED)')
                
                if script_result[1][0][1] == -1:
                    print('VNF IS NOT UP')
                elif script_result[1][0][1] == -2:
                    print('INVALID ACTION REQUESTED')
                else:
                    print("FAILED AT LINE " + str(len(script_result[1][0][1])) + " " + str(script_result[1][0][1][-1]) )
                    if script_result[0]:
                        print('\n-> ERROR RECOVERING SCRIPT (SUCCESS)')
                        for index in range(len(script_result[1][1][1])):
                            print('LINE ' + str(index + 1) + ': ' + str(script_result[1][1][1][index][1]))
                    elif len(script_result[1]) == 2:
                        print('\n-> ERROR RECOVERING SCRIPT (FAILED)')
                        print("FAILED AT LINE " + str(len(script_result[1][1][1])) + " " + str(script_result[1][1][1][-1]) )
            else:
                print('-> NORMAL SCRIPT (SUCCESS)')
                for index in range(len(script_result[1][0][1])):
                    print('LINE ' + str(index + 1) + ': ' + str(script_result[1][0][1][index][1]))
            print('#######################################\n')

        else:
            print('VNF PROMPT COMMAND')

    def complete_vnfscript(self, text, line, begidx, endidx):

        line_arg = line.split(' ')
        if len(line_arg) < 4:
            return PATHCOMPLETER(line, text)

        return []

##################################################################################################################################

##################################################################################################################################
# SFCS INTERFACE
    
    def do_sfcmanagement(self, args):
        if self.prompt.startswith('sfc'):
            splited_args = args.split(' ')
            if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                print('WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED')
                return

            result = self.SFCSERVICE.management(self.SFCEXEC.ID)
            if not result.ok:
                print(result.message)
                return
            for managementData in result.data:
                print(managementData)
        else:
            print('SFC PROMPT COMMAND')

    def do_sfcup(self, args):
        if self.prompt.startswith('sfc'):
            splited_args = args.split(' ')
            if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                print('WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED')
                return

            result = self.SFCSERVICE.up(self.SFCEXEC.ID)
            if not result.ok:
                print(result.message)
                return
        else:
            print('SFC PROMPT COMMAND')

    def do_sfcdown(self, args):
        if self.prompt.startswith('sfc'):
            splited_args = args.split(' ')
            if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                print('WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED')
                return

            result = self.SFCSERVICE.down(self.SFCEXEC.ID)
            if not result.ok:
                print(result.message)
                return
        else:
            print('SFC PROMPT COMMAND')

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
                self.TOPOLOGY.down()
                self.sync_executor()

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
