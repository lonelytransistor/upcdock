from threading import Lock, Thread
from time import sleep
from struct import pack, unpack
import netifaces, socket, zlib

from UPCDock.audioBuffer import AudioBuffer

class SrvMsg:
    MAGICHEADER = b"DEADBEEF"
    PK_KBD = 0
    PK_MOUSE = 1
    PK_MIC = 2
    PK_SPK = 3
    PK_CMD = 4
    PK_SET = 5
    PK_RESEND = 6
    CMD_START_SPK = b"START_SPK"
    CMD_START_MIC = b"START_MIC"
    CMD_HELLO = b"HELLO"
    CMD_QUIT = b"QUIT"
    CMD_ACK = b"ACKNOWLEDGED"
    CMD_ERR = b"ERROR"
    SET_MIC_BUFFER = 1
    SET_SPK_BUFFER = 2
    PADDING = 2048
    MSGNUM = 0
    def __init__(self, t, data, compressed = False, compression = True):
        if (compressed):
            self.data_c = data
            self.data_d = zlib.decompress(data) if compression else data
        else:
            self.data_c = zlib.compress(data) if compression else data
            self.data_d = data
        self.t = t
        self.__class__.MSGNUM = (self.__class__.MSGNUM+1) % 2**8
        self.msg_num = self.__class__.MSGNUM
        self.data_pkt = self.MAGICHEADER + self.msg_num.to_bytes(1, byteorder="big") + (len(self.data_c)+1).to_bytes(4, byteorder="big") + bytes([t]) + self.data_c + bytes(self.PADDING)

class Protocol:
    PORT = 9009
    HID_PATH = "/dev/hidg0"
    UVC_PATH = "/dev/uvc0"
    CONFIG = []
    
    CLIENT = 0xFFFF
    SERVER = 0xFFFE
    
    def __init__(self):
        self.running = True
        self.conns = []
        self.lock = Lock()
        self.msgBuffer = {}
        self.audioLoop = None
        
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        if self.CLIENT in self.CONFIG:
            if SrvMsg.PK_SPK in self.CONFIG:
                self.speaker = AudioBuffer(AudioBuffer.INPUT)
            if SrvMsg.PK_MIC in self.CONFIG:
                self.microphone = AudioBuffer(AudioBuffer.OUTPUT, self._audio_set_remote_buffer)
        elif self.SERVER in self.CONFIG:
            if SrvMsg.PK_SPK in self.CONFIG:
                self.speaker = AudioBuffer(AudioBuffer.OUTPUT, self._audio_set_remote_buffer)
            if SrvMsg.PK_MIC in self.CONFIG:
                self.microphone = AudioBuffer(AudioBuffer.INPUT)
        else:
            raise(Exception("Invalid config!"))
        
        self.f_HID = None
        self.f_UVC = None

    def _writeHID(self, modifiers=None, keysState=None, btn=None, wheel=None, x=None, y=None):
        if not self.f_HID:
            self.f_HID = open(self.HID_PATH, "wb")
            
        if btn!=None and wheel!=None and x!=None and y!=None:
            data = pack("<BBhxHH", 1, btn, wheel, x, y)
        elif keysState!=None and modifiers!=None:
            data = pack("<BBx6s", 3, modifiers, keysState)
        else:
            raise(Exception("Invalid data"))
        
        self.f_HID.write(data)
        self.f_HID.flush()
        
    def _writeUVC(self, data):
        if not self.f_UVC:
            self.f_UVC = open(self.UVC_PATH, "wb")
        self.f_UVC.write(data)
        self.f_UVC.flush()
        
    def send(self, sock, data):
        self.lock.acquire()
        try:
            self.msgBuffer[data.msg_num] = data
            sock.sendall(data.data_pkt)
        except Exception as ex:
            print("Socket exception caught! A race condition may have occured!\n\t", ex)
        self.lock.release()
        
    def sendAll(self, data):
        client_no = 0
        self.lock.acquire()
        conns = self.conns
        self.lock.release()
        for c in conns:
            self.send(c[0], data)
            client_no += 1
        return client_no

    def send_mouse(self, btn, wheel, x, y):
        data = pack("BhHH", btn, wheel, x, y)
        self.sendAll(SrvMsg(SrvMsg.PK_MOUSE, data))
        
    def send_kbd(self, modifiers, keysState):
        data = pack("B6s", modifiers & 0xFF, b''.join([x.to_bytes(1,'big') for x in keysState]))
        self.sendAll(SrvMsg(SrvMsg.PK_KBD, data))
            
    def _audio_set_remote_buffer(self, buffer_size):
        t = Thread(target = self.__audio_set_remote_buffer, args=(buffer_size,))
        t.start()
    def __audio_set_remote_buffer(self, buffer_size):
        if (SrvMsg.PK_MIC in self.CONFIG) and (self.CLIENT in self.CONFIG):
            self.sendAll(SrvMsg(SrvMsg.PK_SET, bytes([SrvMsg.SET_MIC_BUFFER, buffer_size])))
        elif (SrvMsg.PK_SPK in self.CONFIG) and (self.SERVER in self.CONFIG):
            self.sendAll(SrvMsg(SrvMsg.PK_SET, bytes([SrvMsg.SET_SPK_BUFFER, buffer_size])))
        else:
            raise(Exception("Invalid config!"))
    
    def _audio_loop_start(self):
        if self.audioLoop:
            if self.audioLoop.is_alive():
                return
        self.audioLoop = Thread(target = self._audio_loop)
        self.audioLoop.start()
    def _audio_loop(self):
        if self.CLIENT in self.CONFIG:
            pkt = SrvMsg.PK_SPK
            buffer = self.speaker
        elif self.SERVER in self.CONFIG:
            pkt = SrvMsg.PK_MIC
            buffer = self.microphone
        else:
            raise(Exception("Invalid config!"))
        
        while self.running:
            sleep(0.0001)
            
            if buffer.getBufferSize() >= buffer.packet_size:
                try:
                    data = buffer.pop(buffer.packet_size)
                    self.sendAll(SrvMsg(pkt, data))
                except Exception as e:
                    print(e)
            else:
                while (buffer.getBufferSize() == -1):
                    sleep(0.001)
        
    def _loop(self):
        n_conn = len(self.conns)-1
        sock0 = self.conns[n_conn][0]
        rsock = sock0.dup()
        ssock = sock0.dup()
        if self.CLIENT in self.CONFIG:
            self.sendAll(SrvMsg(SrvMsg.PK_CMD, SrvMsg.CMD_HELLO))
            
        if SrvMsg.PK_MIC in self.CONFIG:
            self.sendAll(SrvMsg(SrvMsg.PK_CMD, SrvMsg.CMD_START_MIC))
        if SrvMsg.PK_SPK in self.CONFIG:
            self.sendAll(SrvMsg(SrvMsg.PK_CMD, SrvMsg.CMD_START_SPK))
        #sock.settimeout(0.1)
        
        while self.running:
            try:
                pkt = b""
                while self.running:
                    pkt += rsock.recv(1)
                    pkt = pkt[-len(SrvMsg.MAGICHEADER):]
                    if pkt == SrvMsg.MAGICHEADER:
                        break
                    
                pkt_n = int.from_bytes(rsock.recv(1), byteorder="big")
                pkt_l = int.from_bytes(rsock.recv(4), byteorder="big")+SrvMsg.PADDING
                pkt = b""
                while len(pkt)<pkt_l:
                    if (pkt_l - len(pkt) > 1024):
                        data = rsock.recv(1024)
                        pkt += data
                    else:
                        data = rsock.recv(pkt_l % 1024)
                        pkt += data
                    if (len(data) == 0):
                        print("Corrupted packet! Missing", pkt_l-len(pkt), "bytes. Will attempt to recover data.")
                        break
                
                pkt = SrvMsg(pkt[0], pkt[1:], True)
            except socket.error as e:
                print("Socket error:", e)
                break
            except Exception as e:
                print("Reconstruction failed!", e)
                self.send(ssock, SrvMsg(SrvMsg.PK_CMD, SrvMsg.CMD_ERR))
                continue
            
            if not pkt.t in self.CONFIG:
                print("Unsupported package received.")
                continue
            
            if (pkt.t == SrvMsg.PK_KBD):
                print("SrvMsg.PK_KBD received.")
                modifiers, keysState = unpack("B6s", pkt.data_d)
                self._writeHID(modifiers = modifiers,
                              keysState = keysState)

            elif (pkt.t == SrvMsg.PK_MOUSE):
                print("SrvMsg.PK_MOUSE received.")
                btn, wheel, x, y = unpack("BhHH", pkt.data_d)
                self._writeHID(btn = btn,
                              wheel = wheel,
                              x = x,
                              y = y)
                
            elif (pkt.t == SrvMsg.PK_SPK):
                if not self.speaker.is_active():
                    print("SrvMsg.PK_SPK received but PCM_MIC is inactive.")
                self.speaker.append(pkt.data_d)
                
            elif (pkt.t == SrvMsg.PK_MIC):
                if not self.microphone.is_active():
                    print("SrvMsg.PK_MIC received but PCM_MIC is inactive.")
                self.microphone.append(pkt.data_d)
                
            elif (pkt.t == SrvMsg.PK_SET):
                if (pkt.data_d[0] == SrvMsg.SET_MIC_BUFFER):
                    if SrvMsg.PK_MIC in self.CONFIG:
                        print("SrvMsg.PK_SET SrvMsg.SET_MIC_BUFFER", int(pkt.data_d[1]))
                        self.microphone.setBufferSize(int(pkt.data_d[1]))
                    else:
                        print("Unsupported package received.")
                elif (pkt.data_d[0] == SrvMsg.SET_SPK_BUFFER):
                    if SrvMsg.PK_SPK in self.CONFIG:
                        print("SrvMsg.PK_SET SrvMsg.SET_SPK_BUFFER", int(pkt.data_d[1]))
                        self.speaker.setBufferSize(int(pkt.data_d[1]))
                    else:
                        print("Unsupported package received.")
                    
            elif (pkt.t == SrvMsg.PK_CMD):
                if (pkt.data_d == SrvMsg.CMD_HELLO):
                    print("SrvMsg.CMD_HELLO received.")
                elif (pkt.data_d == SrvMsg.CMD_QUIT):
                    print("SrvMsg.CMD_QUIT received.")
                    break
                elif (pkt.data_d == SrvMsg.CMD_START_SPK):
                    if SrvMsg.PK_SPK in self.CONFIG:
                        if self.SERVER in self.CONFIG:
                            self._audio_loop_start()
                        if not self.speaker.is_active():
                            self.speaker.start()
                    else:
                        print("Client does not serve speaker data.")
                elif (pkt.data_d == SrvMsg.CMD_START_MIC):
                    if SrvMsg.PK_MIC in self.CONFIG:
                        if self.CLIENT in self.CONFIG:
                            self._audio_loop_start()
                        if not self.microphone.is_active():
                            self.microphone.start()
                    else:
                        print("Unsupported package received.")
                elif (pkt.data_d == SrvMsg.CMD_ACK):
                    print("ACK")
                elif (pkt.data_d == SrvMsg.CMD_ERR):
                    print("ERR")
                    
            elif (pkt.t == SrvMsg.PK_RESEND):
                if int(pkt.data_d[0]) in self.msgBuffer.keys():
                    print("SrvMsg.PK_RESEND received.", int(pkt.data_d[0]))
                    self.send(ssock, self.msgBuffer[int(pkt.data_d[0])])
                else:
                    print("Invalid resend message number!", pkt.data_d)
            else:
                print("Unknown packet type.", pkt.t)
                
        print("Connection lost!")
        self.conns.pop(n_conn)
        if (len(self.conns) == 0):
            while self.speaker.is_active() and SrvMsg.PK_SPK in self.CONFIG:
                self.speaker.stop()
                sleep(0.1)
            while self.microphone.is_active() and SrvMsg.PK_MIC in self.CONFIG:
                self.microphone.stop()
                sleep(0.1)
        rsock.close()
        ssock.close()

    def _server_start(self):
        self.sock.bind(("", self.PORT))
        
        while self.running:
            self.sock.listen()
            c, a = self.sock.accept()
            print("Got a connection from:", a, "Forking")
            
            t = Thread(target = self._loop)
            self.conns.append((c, a, t))
            t.start()
    def _client_start(self):
        if self.running:
            for srv in self.srv:
                try:
                    self.sock.connect(srv)
                    break
                except Exception as ex:
                    print("Ignoring invalid IP:", srv, ex)
            print("Connected to:", srv)
            
            t = Thread(target = self._loop)
            self.conns.append((self.sock, srv, t))
            t.start()
    def start(self):
        if self.SERVER in self.CONFIG:
            self._server_start()
        elif self.CLIENT in self.CONFIG:
            self._client_start()
        else:
            raise(Exception("Invalid config!"))
