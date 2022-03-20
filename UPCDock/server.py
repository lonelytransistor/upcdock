from zeroconf import Zeroconf, ServiceInfo
import netifaces, socket

from UPCDock.protocol import Protocol, SrvMsg

def findIPs():
    addresses = []
    for ifaceName in netifaces.interfaces():
        addresses += [socket.inet_aton(i["addr"])
                        for i in netifaces.ifaddresses(ifaceName).setdefault(netifaces.AF_INET, [{"addr": None}])
                        if i["addr"]]
    return addresses
class Server(Protocol):
    TYPE = "_desk-dock._tcp.local."
    NAME = "katsdock"
    
    def __init__(self):
        self.serviceInfo = ServiceInfo(type_=self.TYPE,
                    port=self.PORT, addresses=findIPs(),
                    name=self.NAME+"."+self.TYPE, server=self.NAME+".local.",
                    properties={"version": "1.0"})
        self.zsrv = Zeroconf()
        self.zsrv.register_service(self.serviceInfo)
        
        self.CONFIG = [Protocol.SERVER,
                       SrvMsg.PK_KBD, SrvMsg.PK_MOUSE,
                       SrvMsg.PK_MIC,SrvMsg.PK_SPK,
                       SrvMsg.PK_CMD, SrvMsg.PK_SET, SrvMsg.PK_RESEND]
        super().__init__()
