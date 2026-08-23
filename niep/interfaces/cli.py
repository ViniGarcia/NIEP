from os import listdir
from os.path import commonprefix

import cmd
import readline
import shlex

from niep.domain.result import ResultCode
from niep.application.command import CommandDispatcher
from niep.application.stream import bridge_terminal
from niep.paths import cli_memory_path


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
    except OSError:
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
        self.dispatcher = CommandDispatcher()
        self.VM_ID = None
        self.CONTAINER_ID = None
        self.VNF_ID = None
        self.SFC_ID = None
        self.CLICOMP = None

    def _resource_ids(self, aggregate):
        """Return IDs through the command port, preserving legacy state text."""
        status = self.dispatcher.dispatch('status')
        if not status.ok or not status.data.get('defined'):
            print('NO TOPOLOGY DEFINED')
            return None
        if not status.data.get('up'):
            print('TOPOLOGY IS NOT UP')
            return None
        result = self.dispatcher.dispatch(aggregate, ['list'])
        if not result.ok:
            self.print_result_error(result)
            return None
        return list(result.data or [])

    def _completion_ids(self, aggregate):
        status = self.dispatcher.dispatch('status')
        if not status.ok or not status.data.get('defined') or not status.data.get('up'):
            return None
        result = self.dispatcher.dispatch(aggregate, ['list'])
        return list(result.data or []) if result.ok else []

    def print_result_error(self, result, include_status=False):
        message = result.cli_message(include_status=include_status)
        if message:
            print(message)
        if result.detail and result.detail != message:
            print("DETAIL: " + result.detail)

    def print_define_error(self, result):
        if result.code == ResultCode.PARSER_ERROR:
            print("ERROR: " + result.message + " (DEFINE / PARSER / " + str(result.status) + ")")
            if result.detail:
                print("DETAIL: " + result.detail)
        else:
            print("ERROR: " + result.message + " (DEFINE / EXECUTER /" + str(result.status) + ")")

    def print_vnf_action_result(self, result, action):
        if not result.ok:
            self.print_result_error(result)
            return

        actionstatus = result.data
        if action == 'list':
            print('\n############# ACTION LIST #############')
            actionkeys = list(actionstatus.keys())
            actionkeys.sort()
            for actionkey in actionkeys:
                print(actionkey + " -> " + actionstatus[actionkey])
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

    def print_script_result(self, result):
        if not result.ok:
            self.print_result_error(result)
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
            print('\tcontainer arg -> assumes a container or list the defined ones')
            print('\t\t-> arg = list (list every defined container ID)')
            print('\t\t-> arg = container ID (assumes container prompt)')
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
            print('-> CONTAINER PROMPT <-')
            print('\tcontainerexec command -> execute a non-interactive command')
            print('\tcontainershell [program] -> open an interactive shell (default: /bin/sh)\n')
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

            result = self.dispatcher.dispatch('define', [args])
            if not result.ok:
                self.print_define_error(result)
                return
        else:
            print('NIEP PROMPT COMMAND')

    def complete_define(self, text, line, begidx, endidx):

        return PATHCOMPLETER(line, text)

    def do_topoup(self, args):
        if self.prompt == 'niep> ':
            if args.strip():
                print('WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED')
                return
            result = self.dispatcher.dispatch('topoup')
            if result.code == ResultCode.ALREADY_EXECUTED:
                print(result.message + ' - CODE ' + str(result.status))
                return
            if not result.ok:
                self.print_result_error(result, include_status=True)
        else:
            print('NIEP PROMPT COMMAND')

    def do_topodown(self, args):
        if self.prompt == 'niep> ':
            if args.strip():
                print('WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED')
                return
            result = self.dispatcher.dispatch('topodown')
            if not result.ok:
                self.print_result_error(result, include_status=True)
        else:
            print('NIEP PROMPT COMMAND')

    def do_topoclean(self, args):
        if self.prompt == 'niep> ':
            if args.strip():
                print('WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED')
                return
            result = self.dispatcher.dispatch('topoclean')
            if not result.ok:
                self.print_result_error(result)
            self.VM_ID = self.CONTAINER_ID = self.VNF_ID = self.SFC_ID = None
        else:
            print('NIEP PROMPT COMMAND' )

    def do_topodestroy(self, args):
        if self.prompt == 'niep> ':
            if args.strip():
                print('WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED')
                return
            result = self.dispatcher.dispatch('topodestroy')
            if not result.ok:
                self.print_result_error(result)
            self.VM_ID = self.CONTAINER_ID = self.VNF_ID = self.SFC_ID = None
        else:
            print('NIEP PROMPT COMMAND'  )

    def do_vm(self, args):
        if self.prompt == 'niep> ':
            arguments = args.split()
            if len(arguments) != 1:
                print('WRONG ARGUMENTS AMOUNT - 1 ARGUMENT EXPECTED')
                return
            vm_ids = self._resource_ids('vm')
            if vm_ids is None:
                return
            resource_id = arguments[0]
            if resource_id == 'list':
                print('\n############## VMS LIST ###############')
                for vm_id in vm_ids:
                    print(vm_id)
                print('#######################################\n')
                return
            if resource_id in vm_ids:
                self.changecontext(self.prompt, "vm")
                self.VM_ID = resource_id
                self.prompt = 'vm(' + resource_id + ')> '
                return
            print('VM ' + resource_id + ' NOT FOUND')
        else:
            print('NIEP PROMPT COMMAND')

    def complete_vm(self, text, line, begidx, endidx):

        ids = self._completion_ids('vm')
        if ids is None:
            return []
        if len(ids) == 0:
            return ['list']

        args_list = ['list'] + ids
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

    def do_container(self, args):
        if self.prompt != 'niep> ':
            print('NIEP PROMPT COMMAND')
            return
        arguments = args.split()
        if len(arguments) != 1:
            print('WRONG ARGUMENTS AMOUNT - 1 ARGUMENT EXPECTED')
            return
        container_ids = self._resource_ids('container')
        if container_ids is None:
            return
        resource_id = arguments[0]
        if resource_id == 'list':
            print('\n########### CONTAINERS LIST ###########')
            for container_id in container_ids:
                print(container_id)
            print('#######################################\n')
            return
        if resource_id in container_ids:
            self.changecontext(self.prompt, "container")
            self.CONTAINER_ID = resource_id
            self.prompt = 'container(' + resource_id + ')> '
            return
        print('CONTAINER ' + resource_id + ' NOT FOUND')

    def complete_container(self, text, line, begidx, endidx):
        ids = self._completion_ids('container')
        if ids is None:
            return []
        args_list = ['list'] + ids
        if not text:
            return args_list
        return [item for item in args_list if item.startswith(text)]

    def do_vnf(self, args):
        if self.prompt == 'niep> ':
            arguments = args.split()
            if len(arguments) != 1:
                print('WRONG ARGUMENTS AMOUNT - 1 ARGUMENT EXPECTED')
                return
            vnf_ids = self._resource_ids('vnf')
            if vnf_ids is None:
                return
            resource_id = arguments[0]
            if resource_id == 'list':
                print('\n############## VNFS LIST ##############')
                for vnf_id in vnf_ids:
                    print(vnf_id)
                print('#######################################\n')
                return
            if resource_id in vnf_ids:
                self.changecontext(self.prompt, "vnf")
                self.VNF_ID = resource_id
                self.prompt = 'vnf(' + resource_id + ')> '
                return
            print('VNF ' + resource_id + ' NOT FOUND')
        else:
            print('NIEP PROMPT COMMAND')

    def complete_vnf(self, text, line, begidx, endidx):

        ids = self._completion_ids('vnf')
        if ids is None:
            return []
        if len(ids) == 0:
            return ['list']

        args_list = ['list'] + ids
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
            arguments = args.split()
            if len(arguments) != 1:
                print('WRONG ARGUMENTS AMOUNT - 1 ARGUMENT EXPECTED')
                return
            sfc_ids = self._resource_ids('sfc')
            if sfc_ids is None:
                return
            resource_id = arguments[0]
            if resource_id == 'list':
                print('\n############## SFCS LIST ##############')
                for sfc_id in sfc_ids:
                    print(sfc_id)
                print('#######################################\n')
                return
            if resource_id in sfc_ids:
                self.changecontext(self.prompt, "sfc")
                self.SFC_ID = resource_id
                self.prompt = 'sfc(' + resource_id + ')> '
                return
            print('SFC ' + resource_id + ' NOT FOUND')
        else:
            print('NIEP PROMPT COMMAND')

    def complete_sfc(self, text, line, begidx, endidx):

        ids = self._completion_ids('sfc')
        if ids is None:
            return []
        if len(ids) == 0:
            return ['list']

        args_list = ['list'] + ids
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
            if args.strip():
                print('WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED')
                return
            status = self.dispatcher.dispatch('status')
            if not status.ok or not status.data.get('defined'):
                print('NO TOPOLOGY DEFINED')
                return
            if not status.data.get('up'):
                print('TOPOLOGY IS NOT UP')
                return
            try:
                self.dispatcher.open_mininet_console()
            except RuntimeError as exc:
                print(str(exc))
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

            result = self.dispatcher.dispatch('vm', ['management', self.VM_ID])
            if not result.ok:
                self.print_result_error(result)
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
            self.dispatcher.dispatch('vm', ['ssh', self.VM_ID, splited_args[0], splited_args[1]])
        else:
            print('VM PROMPT COMMAND')

##################################################################################################################################

##################################################################################################################################
# CONTAINER INTERFACE

    def do_containerexec(self, args):
        if not self.prompt.startswith('container'):
            print('CONTAINER PROMPT COMMAND')
            return
        if not args.strip():
            print('WRONG ARGUMENTS AMOUNT - COMMAND EXPECTED')
            return

        try:
            command = shlex.split(args)
        except ValueError as exc:
            print('INVALID COMMAND: ' + str(exc))
            return
        result = self.dispatcher.dispatch('container', ['exec', self.CONTAINER_ID, *command])
        if result.data is not None:
            output = result.data.get('output', '')
            if output:
                print(output, end='' if output.endswith('\n') else '\n')
        if not result.ok:
            self.print_result_error(result, include_status=True)

    def do_containershell(self, args):
        if not self.prompt.startswith('container'):
            print('CONTAINER PROMPT COMMAND')
            return
        try:
            command = shlex.split(args) if args.strip() else ['/bin/sh']
        except ValueError as exc:
            print('INVALID SHELL COMMAND: ' + str(exc))
            return

        result = self.dispatcher.open_stream('container', ['shell', self.CONTAINER_ID, *command])
        if not result.ok:
            self.print_result_error(result)
            return
        stream = result.data
        try:
            bridge_terminal(stream)
        finally:
            try:
                stream.close()
            except Exception:
                pass
        print()

##################################################################################################################################

##################################################################################################################################
# VNFS INTERFACE

    def do_vnfmanagement(self, args):
        if self.prompt.startswith('vnf'):
            splited_args = args.split(' ')
            if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                print('WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED')
                return

            result = self.dispatcher.dispatch('vnf', ['management', self.VNF_ID])
            if not result.ok:
                self.print_result_error(result)
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

            result = self.dispatcher.dispatch('vnf', ['up', self.VNF_ID])
            if not result.ok:
                if result.code == ResultCode.INVALID_VNF_STATUS and isinstance(result.data, dict):
                    print('INVALID VNF STATUS (VNF_STATUS=' + str(result.data.get('VNF_STATUS')) + ', VM_STATUS=' + str(result.data.get('VM_STATUS')) + ')')
                else:
                    self.print_result_error(result)
                return
        else:
            print('VNF PROMPT COMMAND')

    def do_vnfdown(self, args):
        if self.prompt.startswith('vnf'):
            splited_args = args.split(' ')
            if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                print('WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED')
                return

            result = self.dispatcher.dispatch('vnf', ['down', self.VNF_ID])
            if not result.ok:
                self.print_result_error(result)
                return
        else:
            print('VNF PROMPT COMMAND')

    def do_vnfaction(self, args):
        if self.prompt.startswith('vnf'):
            splited_args = args.split(' ')
            if len(splited_args) > 2 or len(splited_args) == 1 and len(splited_args[0]) == 0:
                print('WRONG ARGUMENTS AMOUNT - 1 OR 2 ARGUMENTS EXPECTED')
                return

            if len(splited_args) > 0:
                result = self.dispatcher.dispatch('vnf', ['action', self.VNF_ID, splited_args[0], *splited_args[1:]])
                self.print_vnf_action_result(result, splited_args[0])

        else:
            print('VNF PROMPT COMMAND')

    def complete_vnfaction(self, text, line, begidx, endidx):

        status = self.dispatcher.vnf_actions(self.VNF_ID)
        args_list = sorted((status.data or {}).keys()) if status.ok and isinstance(status.data, dict) else []

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
                result = self.dispatcher.dispatch('vnf', ['script', self.VNF_ID, splited_args[0]])
            else:
                result = self.dispatcher.dispatch('vnf', ['script', self.VNF_ID, splited_args[0], splited_args[1]])

            self.print_script_result(result)

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

            result = self.dispatcher.dispatch('sfc', ['management', self.SFC_ID])
            if not result.ok:
                self.print_result_error(result)
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

            result = self.dispatcher.dispatch('sfc', ['up', self.SFC_ID])
            if not result.ok:
                self.print_result_error(result)
                return
        else:
            print('SFC PROMPT COMMAND')

    def do_sfcdown(self, args):
        if self.prompt.startswith('sfc'):
            splited_args = args.split(' ')
            if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                print('WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED')
                return

            result = self.dispatcher.dispatch('sfc', ['down', self.SFC_ID])
            if not result.ok:
                self.print_result_error(result)
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

        status = self.dispatcher.dispatch('status')
        if status.ok and status.data.get('up'):
            self.dispatcher.dispatch('topodown')

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
            readline.read_history_file(str(cli_memory_path("NIEPMEM")))
            return True
        except Exception:
            return False

    def postloop(self):
        try:
            if self.prompt.startswith("niep"):
                readline.write_history_file(str(cli_memory_path("NIEPMEM")))
            elif self.prompt.startswith("vm"):
                readline.write_history_file(str(cli_memory_path("VMMEM")))
            elif self.prompt.startswith("container"):
                readline.write_history_file(str(cli_memory_path("CONTAINERMEM")))
            elif self.prompt.startswith("vnf"):
                readline.write_history_file(str(cli_memory_path("VNFMEM")))
            elif self.prompt.startswith("sfc"):
                readline.write_history_file(str(cli_memory_path("SFCMEM")))
            return True
        except Exception:
            return False

    def changecontext(self, current, succeeding):
        try:
            if current.startswith("niep"):
                readline.write_history_file(str(cli_memory_path("NIEPMEM")))
            elif current.startswith("vm"):
                readline.write_history_file(str(cli_memory_path("VMMEM")))
            elif current.startswith("container"):
                readline.write_history_file(str(cli_memory_path("CONTAINERMEM")))
            elif current.startswith("vnf"):
                readline.write_history_file(str(cli_memory_path("VNFMEM")))
            elif current.startswith("sfc"):
                readline.write_history_file(str(cli_memory_path("SFCMEM")))


            readline.clear_history()

            if succeeding.startswith("niep"):
                readline.read_history_file(str(cli_memory_path("NIEPMEM")))
            elif succeeding.startswith("vm"):
                readline.read_history_file(str(cli_memory_path("VMMEM")))
            elif succeeding.startswith("container"):
                readline.read_history_file(str(cli_memory_path("CONTAINERMEM")))
            elif succeeding.startswith("vnf"):
                readline.read_history_file(str(cli_memory_path("VNFMEM")))
            elif succeeding.startswith("sfc"):
                readline.read_history_file(str(cli_memory_path("SFCMEM")))

            return True
        except Exception:
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
