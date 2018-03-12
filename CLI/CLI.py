from cmd import Cmd
from sys import path
from os.path import isfile
from mininet.cli import CLI
path.insert(0, '../TOPO-MAN/')
from Executer import Executer
from Parser import PlatformParser

#VAI FALTAR:
# Criação assistida
# Inteface Grafica
# Scripts do PyCoo

class NIEPCLI(Cmd):

    prompt = 'niep > '
    NIEPEXE = None
    VNFEXEC = None
    SFCEXEC = None

##################################################################################################################################
# NIEP INTERFACE

    def do_help(self, args):
        if self.prompt == 'niep > ':
            print 'TO DO'
        else:
            print 'NIEP PROMPT COMMAND'
    
    def do_define(self, args):
        if self.prompt == 'niep > ':
            splited_args = args.split(' ')
            if not len(splited_args) == 1:
                print 'WRONG ARGUMENTS AMOUNT - 1 ARGUMENT EXPECTED'
                return

            self.NIEPEXE = Executer(PlatformParser(args))
            if not self.NIEPEXE.STATUS == None:
                self.NIEPEXE = None
                return 
        else:
            print 'NIEP PROMPT COMMAND'

    def do_topoup(self, args):
        if self.prompt == 'niep > ':
            if not self.NIEPEXE == None: 
                splited_args = args.split(' ')
                if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                    print 'WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED'
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
        if self.prompt == 'niep > ':
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
        if self.prompt == 'niep > ':
            if not self.NIEPEXE == None: 
                print 'TO DO'

            else:
                print 'NO TOPOLOGY DEFINED'
        else:
            print 'NIEP PROMPT COMMAND' 

    def do_vnf(self, args):
        if self.prompt == 'niep > ':
            if not self.NIEPEXE == None:
                if not self.NIEPEXE.STATUS == 0:
                    print 'TOPOLOGY IS NOT UP'
                    return

                splited_args = args.split(' ')
                if not len(splited_args) == 1:
                    print 'WRONG ARGUMENTS AMOUNT - 1 ARGUMENT EXPECTED'
                    return
                
                if args == 'list':
                    print '############## VNFS LIST ##############'
                    for VNF in self.NIEPEXE.VNFS:
                        print VNF
                    print '#######################################'
                    return

                if args in self.NIEPEXE.VNFS:
                    self.VNFEXEC = self.NIEPEXE.VNFS[args]
                    self.prompt = 'vnf(' + args + ') > '
                    return
                else:
                     print 'VNF ' + args + ' NOT FOUND'
            else:
                print 'NO TOPOLOGY DEFINED'
        else:
            print 'NIEP PROMPT COMMAND'

    def do_sfc(self, args):
        if self.prompt == 'niep > ':
            if not self.NIEPEXE == None:
                if not self.NIEPEXE.STATUS == 0:
                    print 'TOPOLOGY IS NOT UP'
                    return

                splited_args = args.split(' ')
                if not len(splited_args) == 1:
                    print 'WRONG ARGUMENTS AMOUNT - 1 ARGUMENT EXPECTED'
                    return
                
                if args == 'list':
                    print '############## SFCS LIST ##############'
                    for SFC in self.NIEPEXE.CONFIGURATION.SFCS:
                        print SFC.ID
                    print '#######################################'
                    return

                for SFC in self.NIEPEXE.CONFIGURATION.SFCS:
                    if args == SFC.ID:
                        self.SFCEXEC = SFC
                        self.prompt = 'sfc(' + args + ') > ' 
                        return
                print 'SFC ' + args + ' NOT FOUND'
            else:
                print 'NO TOPOLOGY DEFINED'
        else:
            print 'NIEP PROMPT COMMAND'

    def do_mininet(self, args):
        if self.prompt == 'niep > ':
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

    def do_management(self, args):
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
        splited_args = args.split(' ')
        if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
            print 'WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED'
            return

        if self.prompt.startswith('vnf'):
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
            if len(splited_args) == 1 and not len(splited_args[0]) == 0 or len(splited_args) > 1:
                print 'WRONG ARGUMENTS AMOUNT - 0 ARGUMENTS EXPECTED'
                return

        else:
            print 'VNF PROMPT COMMAND'

    def do_vnfaction(self, args):
        if self.prompt.startswith('vnf'):

        else:
            print 'VNF PROMPT COMMAND'

##################################################################################################################################

##################################################################################################################################
# SFCS INTERFACE

    def do_sfcup(self, args):
        if self.prompt.startswith('sfc'):
            print 'TO DO'
        else:
            print 'SFC PROMPT COMMAND'

    def do_sfcdown(self, args):
        if self.prompt.startswith('sfc'):
            print 'TO DO'
        else:
            print 'SFC PROMPT COMMAND'

##################################################################################################################################

##################################################################################################################################
# GLOBAL CALL FOR CLI

    def do_exit(self, args):
        if not self.prompt == 'niep > ':
            self.prompt = 'niep > '
            return

        if not self.NIEPEXE == None:
            if self.NIEPEXE.STATUS == 0:
                self.NIEPEXE.topologyDown()

        exit()
        return True

    def do_EOF(self, args):
        return True
    
    def postloop(self):
        print ''
        return True

##################################################################################################################################

if __name__ == '__main__':
    NIEPCLI().cmdloop()