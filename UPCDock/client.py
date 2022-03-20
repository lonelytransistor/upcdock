from zeroconf import Zeroconf

from UPCDock.protocol import Protocol, SrvMsg

class Client(Protocol):
    TYPE = "_desk-dock._tcp.local."
    NAME = "katsdock"
    
    def __init__(self, ip=""):
        self.zsrv = Zeroconf()
        self.srv = []
        if ip == "":
            for srv in [self.zsrv.get_service_info(self.TYPE, self.NAME + '.' + self.TYPE)]:
                try:
                    for ip in srv.addresses:
                        self.srv.append((socket.inet_ntoa(ip), srv.port))
                except Exception as ex:
                    print("Error while parsing", srv)
        else:
            self.srv.append((ip, self.PORT))
            
        if not len(self.srv) > 0:
            raise(Exception("No server found."))
        
        self.CONFIG = [Protocol.CLIENT,
                       SrvMsg.PK_KBD, SrvMsg.PK_MOUSE,
                       SrvMsg.PK_MIC,SrvMsg.PK_SPK,
                       SrvMsg.PK_CMD, SrvMsg.PK_SET, SrvMsg.PK_RESEND]
        super().__init__()
