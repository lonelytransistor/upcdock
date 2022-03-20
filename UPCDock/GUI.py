from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QApplication, QMainWindow, QSizePolicy, QDockWidget, QGridLayout, QPushButton, QStyle
from PyQt5.QtMultimedia import QCamera, QCameraInfo
from PyQt5.QtMultimediaWidgets import QCameraViewfinder
from threading import Lock

from UPCDock.client import Client

class GUI(QCameraViewfinder):
    DONT_COVER_TASKBAR = (Qt.FramelessWindowHint |
                          Qt.MaximizeUsingFullscreenGeometryHint |
                          Qt.CustomizeWindowHint)
    COVER_TASKBAR =      (Qt.FramelessWindowHint |
                          Qt.WindowStaysOnTopHint |
                          Qt.MaximizeUsingFullscreenGeometryHint |
                          Qt.CustomizeWindowHint)
    ICON_SIZE = 48
    
    def __init__(self, width = 2560, height = 1440):
        self.app = QApplication([])
        self.client = Client("192.168.2.138")
        super().__init__()
        
        self.width = width
        self.height = height
        size = self.app.primaryScreen().size()
        self.screenWidth, self.screenHeight = (size.width(), size.height())
        
        self.setFixedWidth(self.width)
        self.setFixedHeight(self.height)
        self.setMouseTracking(True)
        self.grabKeyboard()
        
        self.mouse_x = 0
        self.mouse_y = 0
        self.mouse_w = 0
        self.mouse_b = 0
        self.kbdState = []
        self.lock = Lock()
        
        cam_link = [x for x in QCameraInfo.availableCameras() if "Cam Link 4K" in x.description()]
        if len(cam_link) > 0:
            self.captureCard = QCamera(cam_link[0].position())
            self.captureCard.setViewfinder(self)
            self.captureCard.setCaptureMode(QCamera.CaptureVideo)
            self.captureCard.load()
            self.captureCard.start()
        
        self.dockGrid = QGridLayout()
        self.dockButtons = ["SP_TitleBarCloseButton", "SP_TitleBarMinButton", "SP_DriveDVDIcon"]
        self._dockButtons = []
        for i in range(len(self.dockButtons)):
            btn = QPushButton("", self)
            btn.setGeometry(self.width, i*self.ICON_SIZE, self.ICON_SIZE, self.ICON_SIZE)
            btn.setIcon(btn.style().standardIcon(getattr(QStyle, self.dockButtons[i])))
            self.dockGrid.addWidget(btn)
            self._dockButtons.append(btn)
        
        self.win = QMainWindow()
        self.win.setWindowTitle("Kat's dock")
        self.win.setCentralWidget(self)
        self.win.setWindowFlags(self.COVER_TASKBAR)
        self.win.setGeometry(self.screenWidth-self.width-self.ICON_SIZE, 0, self.width+self.ICON_SIZE, self.height)
        self.win.setFixedWidth(self.width+self.ICON_SIZE)
        self.win.setFixedHeight(self.height)
        self.win.setLayout(self.dockGrid)
        
        self.app.applicationStateChanged.connect(self.applicationStateChanged)
        self.appCoversTaskbar = True
        self.appStateInhibit = False
        
    def coverTaskbar(self, state):
        if state:
            if not self.appCoversTaskbar:
                self.appStateInhibit = True
                self.win.setWindowFlags(self.COVER_TASKBAR)
                self.win.show()
                self.appStateInhibit = False
                self.appCoversTaskbar = True
        else:
            if self.appCoversTaskbar:
                self.appStateInhibit = True
                self.win.setWindowFlags(self.DONT_COVER_TASKBAR)
                self.win.show()
                self.appStateInhibit = False
                self.appCoversTaskbar = False
    def applicationStateChanged(self, state):
        if (state == Qt.ApplicationInactive) and not self.appStateInhibit:
            self.coverTaskbar(False)
        
    def show(self):
        self.win.show()
    def start(self):
        self.show()
        self.client.start()
        self.app.exec_()
    
    def postMousePacket(self):
        self.client.send_mouse(self.mouse_b, self.mouse_w, self.mouse_x, self.mouse_y)
    def postKbdPacket(self):
        kbd_mod = int(self.app.queryKeyboardModifiers())>>(3*8) & 0xFF
        self.client.send_kbd(kbd_mod, self.kbdState)

    def keyPressEvent(self, e):
        keycode = e.nativeVirtualKey() #self.keycode2HID(e.key())
        if not keycode in self.kbdState:
            self.lock.acquire()
            self.kbdState.append(keycode)
            self.lock.release()
            print(keycode)
            #self.postKbdPacket()
    def keyReleaseEvent(self, e):
        keycode = e.nativeVirtualKey() #self.keycode2HID(e.key())
        if (not e.isAutoRepeat()) and (keycode in self.kbdState):
            self.lock.acquire()
            self.kbdState.remove(keycode)
            self.lock.release()
            print(keycode)
            #self.postKbdPacket()
    def _mouseEvent(self, e):
        if (self.appCoversTaskbar):
            self.mouse_x = clamp(0, 10000, int(10000*e.x()/2560))
            self.mouse_y = clamp(0, 10000, int(10000*e.y()/1440))
            self.mouse_b = int(e.buttons()) & 0xFF
            self.postMousePacket()
    def mouseMoveEvent(self, e):
        self._mouseEvent(e)
    def mousePressEvent(self, e):
        self._mouseEvent(e)
    def mouseReleaseEvent(self, e):
        if (self.appCoversTaskbar):
            self._mouseEvent(e)
        else:
            self.coverTaskbar(True)
    def wheelEvent(self, e):
        self.mouse_w = e.pixelDelta().y()>>5
        self.postMousePacket()
