from math import ceil, floor
from threading import Lock
import pyaudio

def clamp(minimum, x, maximum):
    return max(minimum, min(x, maximum))
def splitList(l, size):
    return [
        l[i * size:(i * size) + size]
        for i in range(ceil(len(l) / size))
    ]
def stretchBytes(bytes_buf, l):
    missing = l - len(bytes_buf)
    spacing = int(ceil(len(bytes_buf)/missing))
    padding = float(missing)/len(bytes_buf)
    padding2 = 0
    if (padding % 1.0):
        padding2 = int(floor((len(bytes_buf)/spacing)*(padding % 1.0)))
    padding = int(floor(padding))
    
    bytes_buf2 = b""
    ix = 0
    for slist in splitList(bytes_buf, spacing):
        bytes_buf2 += slist + bytes([slist[-1]*padding])
        if (ix == padding2):
            bytes_buf2 += bytes([slist[-1]])
            ix = 0
        else:
            ix += 1
    if len(bytes_buf2) < l:
        bytes_buf2 += bytes([bytes_buf2[-1]*(l-len(bytes_buf2))])
    elif len(bytes_buf2) > l:
        bytes_buf2 = bytes_buf2[:l]
    return bytes_buf2


class AudioBuffer:
    INPUT = 0x00
    OUTPUT = 0x01
    
    def __init__(self, t, buffer_ctrl=None, buffer_size_int=2, buffer_size_min=4, buffer_size_max=30, buffer_recalc_speed = 240):
        self.lock = Lock()
        self.frames = 441*buffer_size_int
        self.packet_size = self.frames*buffer_size_min
        self.buffer_size_min = buffer_size_min+2
        self.buffer_size_max = buffer_size_max
        self.buffer_size = buffer_size_min
        self.buffer = b"0"*self.buffer_size*self.packet_size
        self.backup_data = b"0"*self.buffer_size*self.packet_size
        self.interpolated_data = b"0"*self.buffer_size*self.packet_size
        
        self.t = t
        self.buffer_underflow = 0
        self.buffer_ctrl = buffer_ctrl
        self.buffer_recalc_min = self.buffer_size
        self.buffer_recalc_max = 0
        self.buffer_recalc_timer = 0
        self.buffer_recalc_speed = buffer_recalc_speed
        
        self.pyAudio = pyaudio.PyAudio()
        self.PCM = self.pyAudio.open(start=False, format=pyaudio.paInt16,
                                     channels=2, rate=44100,
                                     input=(self.t==self.INPUT), output=(self.t==self.OUTPUT),
                                     frames_per_buffer=self.frames, stream_callback=self.cb)
    
    def setBufferSize(self, buffer_size):
        self.lock.acquire()
        
        if buffer_size*self.frames > len(self.buffer):
            self.buffer_underflow = 1
        self.buffer = self.buffer[-buffer_size*self.frames:]
        self.buffer_size = buffer_size
        
        self.updateBufferQuality(True)
        self.lock.release()
        
    def stretchBuffer(self, l):
        #self.buffer = stretchBytes(self.buffer, l)
        print("Buffer stretched1", len(self.buffer))
        self.buffer = self.buffer*int(l//len(self.buffer))
        self.buffer += b"0"*(l-len(self.buffer))
        print("Buffer stretched2", len(self.buffer))
        
    def start(self):
        self.PCM.start_stream()
    def stop(self):
        self.PCM.stop_stream()
    def is_active(self):
        return self.PCM.is_active()
        
    def getBufferSize(self):
        self.lock.acquire()
        ret = len(self.buffer) if self.buffer_underflow == 0 else -1
        self.lock.release()
        return ret
        
    def updateBufferQuality(self, clear=False):
        buffer_size_new = 0
        if self.buffer_ctrl:
            if self.buffer_recalc_timer > self.buffer_recalc_speed:
                if self.buffer_recalc_min>2 or self.buffer_recalc_max<(self.buffer_size-2):
                    buffer_size_new = self.buffer_size-min(self.buffer_recalc_min, self.buffer_size-self.buffer_recalc_max)+2
                
            if clear or self.buffer_recalc_timer > self.buffer_recalc_speed:
                self.buffer_recalc_min = self.buffer_size
                self.buffer_recalc_max = 0
                self.buffer_recalc_timer = 0
            else:
                self.buffer_recalc_min = min(self.buffer_recalc_min, self.buffer_size-len(self.buffer)//self.frames)
                self.buffer_recalc_max = max(self.buffer_recalc_max, len(self.buffer)//self.frames)
                self.buffer_recalc_timer += 1
        if (buffer_size_new > self.buffer_size_min) and (buffer_size_new < self.buffer_size_max) and (buffer_size_new != self.buffer_size):
            return buffer_size_new
        else:
            return 0
    
    def append(self, data):
        self.lock.acquire()
        self.buffer += data
        
        if len(self.buffer)>(self.buffer_size-1)*self.frames and self.buffer_underflow:
                self.updateBufferQuality(True)
                self.buffer_underflow = 0
        if len(self.buffer) > self.buffer_size*self.frames:
            self.buffer = self.buffer[-self.buffer_size*self.frames:]
        self.lock.release()
        
        if buffer_size := self.updateBufferQuality():
            print("Buffer adjusted from", self.buffer_size, "to", buffer_size, "; current delay =", len(self.buffer)/44.1, "ms", "; will be =", self.buffer_size*self.frames/44.1, "ms")
            self.buffer_size = buffer_size
            self.buffer_ctrl(self.buffer_size)
            
    def pop(self, l):
        self.lock.acquire()
        data = self.buffer[0:l]
        if len(self.buffer) > 4*l and self.buffer_underflow == 2:
            print("Buffer underflow prevented.")
            self.buffer_underflow = 0
        if len(self.buffer) < 2*l and self.buffer_underflow == 0:
            if self.buffer_ctrl:
                buffer_size = self.buffer_size+1
                if (buffer_size < self.buffer_size_max):
                    self.buffer_underflow = 2
                    print("Buffer adjusted from", self.buffer_size, "to", buffer_size, "; current delay =", len(self.buffer)/44.1, "ms", "; will be =", self.buffer_size*self.frames/44.1, "ms")
                    self.updateBufferQuality(True)
                    self.buffer_size = buffer_size
                    self.buffer_ctrl(self.buffer_size)
        if len(self.buffer) < l:
            self.buffer_underflow = 1
            data = self.backup_data[0:l]
            data += b"0"*(l-len(data))
            self.backup_data = self.backup_data[l:]
            self.buffer = b""
        else:
            self.backup_data += data
            self.backup_data = self.backup_data[-4*l:]
        if self.buffer_underflow != 1:
            self.buffer = self.buffer[l:]
        self.lock.release()
        
        return data

    def cb(self, in_data, frame_count, time_info, status_flags):
        self.packet_size = frame_count*2*2
        if in_data is None:
            data = self.pop(frame_count*2*2)
            return (data, pyaudio.paContinue)
        else:
            self.append(in_data)
            return (None, pyaudio.paContinue)
