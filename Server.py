import sys
sys.path.append("/usr/libexec/upcdock/")
sys.path.append(".")

from UPCDock.server import Server
mServer = Server()
mServer.start()
