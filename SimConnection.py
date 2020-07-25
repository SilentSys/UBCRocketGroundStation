import os
import subprocess as sp
import threading
from enum import Enum

from IConnection import IConnection
from StreamLogger import StreamLogger
from XBeeModuleSim import XBeeModuleSim


class SimPacketId(Enum):
    CONFIG = 0x01
    BUZZER = 0x07
    DIGITAL_PIN_WRITE = 0x50
    RADIO = 0x52


LOG_HISTORY_SIZE = 100


class SimConnection(IConnection):
    def __init__(self, firmwareDir, executableName):
        self.executablePath = os.path.join(firmwareDir, executableName)
        self.firmwareDir = firmwareDir
        self.callback = None

        self.bigEndianInts = None
        self.bigEndianFloats = None

        # Firmware subprocess - Closes automatically when parent (ground station) closes
        self.rocket = sp.Popen(
            self.executablePath, cwd=self.firmwareDir, stdin=sp.PIPE, stdout=sp.PIPE
        )
        self.stdout = StreamLogger(self.rocket.stdout, LOG_HISTORY_SIZE)
        self._rocket_handshake()

        # Gets endianess of ints and floats
        self._getEndianness()

        # Thread to make communication non-blocking
        self.thread = threading.Thread(target=self._run, name="SIM", daemon=True)
        self.thread.start()

        self._xbee = XBeeModuleSim()
        self._xbee.rocket_callback = self._send_radio_sim
    
    def _rocket_handshake(self):
        assert self.stdout.read(3) == b"SYN"
        # Uncomment for FW debuggers, for a chance to attach debugger
        # input("Recieved rocket SYN; press enter to respond with ACK and continue\n")
        self.rocket.stdin.write(b"ACK")
        self.rocket.stdin.flush()
        
    def send(self, data):
        self._xbee.send_to_rocket(data)

    def _send_radio_sim(self, data):
        packet = b"R"
        packet += len(data).to_bytes(length=2, byteorder="big")
        packet += data

        for b in packet:  # Work around for windows turning LF to CRLF
            self.rocket.stdin.write(bytes([b]))
        self.rocket.stdin.flush()

    def registerCallback(self, fn):
        self._xbee.ground_callback = fn

    # Returns whether ints should be decoded as big endian
    def isIntBigEndian(self):  # must be thead safe
        assert self.bigEndianInts is not None
        return self.bigEndianInts

    # Returns whether floats should be decoded as big endian
    def isFloatBigEndian(self):
        assert self.bigEndianFloats is not None
        return self.bigEndianFloats

    def shutDown(self):
        self.rocket.kill()  # Otherwise it will prevent process from closing

    # AKA handle "Config" packet
    def _getEndianness(self):
        id = self.stdout.read(1)[0]
        assert id == SimPacketId.CONFIG.value

        length = self._getLength()
        assert length == 8
        data = self.stdout.read(length)

        self.bigEndianInts = data[0] == 0x04
        self.bigEndianFloats = data[4] == 0xC0

        print(
            "SIM: Big Endian Ints - %s, Big Endian Floats - %s"
            % (self.bigEndianInts, self.bigEndianFloats)
        )

    def _handleBuzzer(self):
        length = self._getLength()
        assert length == 1
        data = self.stdout.read(length)

        songType = int(data[0])
        print("SIM: Bell rang with song type %s" % songType)

    def _handleDigitalPinWrite(self):
        length = self._getLength()
        assert length == 2
        [pin, value] = self.stdout.read(2)

        print("SIM: Pin %s set to %s" % (pin, value))

    def _handleRadio(self):
        length = self._getLength()
        data = self.stdout.read(length)
        self._xbee.recieved_from_rocket(data)

    packetHandlers = {
        # DO NOT HANDLE "CONFIG" - it should be received only once at the start
        SimPacketId.BUZZER.value: _handleBuzzer,
        SimPacketId.DIGITAL_PIN_WRITE.value: _handleDigitalPinWrite,
        SimPacketId.RADIO.value: _handleRadio,
    }

    def _run(self):
        while True:
            try:
                id = self.stdout.read(1)[0]  # Returns 0 if process

                if id not in SimConnection.packetHandlers.keys():
                    print("SIM protocol violation!!! Shutting down.")
                    for b in self.stdout.getHistory():
                        print(hex(b))
                    print("^^^^ violation.")
                    continue

                # Call packet handler
                SimConnection.packetHandlers[id](self)
            except IndexError as ex:
                if self.rocket.poll() is not None:  # Process was killed
                    return

    def _getLength(self):
        [msb, lsb] = self.stdout.read(2)
        return (msb << 8) | lsb