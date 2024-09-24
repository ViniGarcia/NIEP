import sys
from CLI import NIEPCLI

CLICONTROL = NIEPCLI()
CLICONTROL.do_define(sys.argv[1])
CLICONTROL.do_topoup("")
CLICONTROL.cmdloop()

