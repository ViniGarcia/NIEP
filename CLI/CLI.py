from cmd import Cmd
from sys import path
from os.path import isfile
path.insert(0, '../TOPO-MAN/')
from Executer import Executer
from Parser import PlatformParser

class CLI(Cmd):

    prompt = 'niep > '
    NIEPEXE = None
    VNFEXEC = None
    SFCEXEC = None

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

    def do_up(self, args):
        if self.prompt == 'niep > ':
            if not self.NIEPEXE == None: 
                splited_args = args.split(' ')
                if not len(splited_args) == 1 and not len(splited_args[0]) == 0:
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

    def do_down(self, args):
        if self.prompt == 'niep > ':
            if not self.NIEPEXE == None: 
                splited_args = args.split(' ')
                if not len(splited_args) == 1 and not len(splited_args[0]) == 0:
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
                    print '\n############## VNFS LIST ##############'
                    for VNF in self.NIEPEXE.VNFS:
                        print VNF
                    print '#######################################\n'
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
                    print '\n############## SFCS LIST ##############'
                    for SFC in self.NIEPEXE.CONFIGURATION.SFCS:
                        print SFC.ID
                    print '#######################################\n'
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

    def do_mn(self, args):
        if self.prompt == 'niep > ':
            print 'TO DO'
        else:
            print 'NIEP PROMPT COMMAND'

    def do_niep(self, args):
        self.prompt = 'niep > '

    def do_exit(self, args):
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

if __name__ == '__main__':
    CLI().cmdloop()