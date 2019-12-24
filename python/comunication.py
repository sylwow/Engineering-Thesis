import asyncio
import logging
import threading
from builtins import object
import time
from enum import Enum
from bleak import _logger as logger
from bleak import BleakClient


def main(ble):
    print("starting low level comunication")
    loop = asyncio.new_event_loop()
    loop.run_until_complete(ble.run(loop))


class Commands(object):
    """command executor class it sends commands, check them and maintain errors"""

    class commands(Enum):
        stop = 15
        start = 16
        eg1 = 1
        eg2 = 2

    class additionalInfo(Enum):
        empty = 1
        commandStarted = 2
        commandEnded = 3
        commandError = 4
        MobileRobotError = 5
        RobotReady = 6
        accessDenyed = 7

    class deviceId(Enum):
        pc = 2
        mobileRobot = 1

    class robotWatchDog(object):
        """command timers waiting for proper execution"""

        class commandState(Enum):
            sending = 1
            executing = 2
            done = 3

        class commandTimes(Enum):
            """in sec"""
            sendingTime = 10
            executingTime = 30

        def __init__(self, command, commandId, mainPtr):
            self.mainPtr = mainPtr
            self.command = command
            self.commandId = commandId
            self.state = self.commandState.sending
            self.timer = threading.Timer(self.commandTimes.sendingTime.value, self)
            self.timer.start()

        def __call__(self):
            print("Command: {}, id {}. Command time is up, robot did not changed {} state\n".format(self.command,
                                                                                                    self.commandId,
                                                                                                    self.state))
            self.mainPtr.delete(self)

    def __init__(self):
        self.comunicator = None

        self.messageId = 1
        self.commandId = 1
        self.ble = BleComunicator(self.gotData)
        self.watchDog = []

    def run(self):
        print("running thread for low level comunicator")
        self.comunicator = threading.Thread(target=main, args=(self.ble,), daemon=True)
        self.comunicator.start()

    def delete(self, ptr):
        self.watchDog.remove(ptr)

    def executeCommand(self, command):
        data = bytearray(
            [self.deviceId.pc.value, command.value, self.commandId, self.messageId, self.additionalInfo.empty.value])
        print(data)
        self.watchDog.append(self.robotWatchDog(command, self.commandId, self))
        self.ble.setData(data)
        self.commandId %= 255
        self.messageId %= 255
        self.messageId += 1
        self.commandId += 1
        print("Command initialization")

    def gotData(self, data):
        #print("got data" + str(data))
        try:
            self.checkData(data)
        except Exception as e:
            print("An exception occurred while getting data: " + str(e))
        finally:
            pass

    def disconnect(self):
        self.ble.disconnect()

    def checkData(self, data):
        deviceId = self.deviceId(data[0])
        command = self.commands(data[1])
        commandId = data[2]
        messageId = data[3]
        additionalInfo = self.additionalInfo(data[4])
        # print("{} {} {} {} {}".format(deviceId, messageId, additionalInfo, command, commandId))
        if self.checkAdditionalInfo(deviceId, command, commandId, messageId, additionalInfo):
            return
        if deviceId != self.deviceId.mobileRobot:
            print("Wrong device Id, should be 1 - mobile Robot")
        if additionalInfo == self.additionalInfo.commandError:
            print("Command error (robot): {}, id {}".format(command, commandId))
        if additionalInfo == self.additionalInfo.MobileRobotError:
            print("Robot error")
        found = False
        for watchDog in self.watchDog:
            if commandId == watchDog.commandId:
                watchDog.timer.cancel()
                found = True
                if additionalInfo == self.additionalInfo.commandStarted:
                    watchDog.state = self.robotWatchDog.commandState.executing
                    watchDog.timer = threading.Timer(self.robotWatchDog.commandTimes.executingTime.value, watchDog)
                    watchDog.timer.start()
                    print("Command under execution")
                elif additionalInfo == self.additionalInfo.commandEnded:
                    watchDog.state = self.robotWatchDog.commandState.done
                    print("Command executed")
                    watchDog.timer.cancel()
                    self.delete(watchDog)
                    break
        if not found:
            print("None of watchdog commands found, error")

    def checkAdditionalInfo(self, deviceId, command, commandId, messageId, additionalInfo):
        if additionalInfo == self.additionalInfo.empty:
            return False
        elif additionalInfo == self.additionalInfo.commandError:
            print("Command error occurred, id {}".format(commandId))
            return True
        elif additionalInfo == self.additionalInfo.accessDenyed:
            print("Access to robot denied, wrong security code sended")
            return True
        elif additionalInfo == self.additionalInfo.RobotReady:
            print("Robot is ready")
            return True
        elif additionalInfo == self.additionalInfo.MobileRobotError:
            print("Mobile robot error")
            return True
        else:
            return False


class BleComunicator(object):
    """bluetooth low level comunicator"""

    def __init__(self, fnct):
        self.connected = False
        self.address = "01:02:03:04:1A:DF"  ##bluetooth mac address
        self.secourityCode = b'QV9GVE3SYFJ8768CCNL'
        self.uartUUID = "0000ffe1-0000-1000-8000-00805f9b34fb"  ##transmision characteristic
        self.data = b''
        self.event = threading.Event()
        self.onDataFunction = fnct
        self.disc = False

    def setData(self, data):
        self.data = data
        self.event.set()

    def disconnect(self):
        self.disc = True
        self.event.set()

    async def run(self, loop):
        try:
            async with BleakClient(self.address, loop=loop) as client:
                # client.set_disconnected_callback(self.disconnected)
                x = await client.is_connected()
                print("Connected to mobileRobot")
                await client.write_gatt_char(self.uartUUID, self.secourityCode)
                await client.start_notify(self.uartUUID, self.getData)
                while True:
                    self.event.wait()
                    if self.disc:
                        break
                    await client.write_gatt_char(self.uartUUID, self.data)
                    self.event.clear()
        except Exception as e:
            print("An exception occurred: " + str(e))
        finally:
            print("Disconnected")

    def getData(self, sender, data):
        self.onDataFunction(data)


if __name__ == "__main__":
    command = Commands()
    command.run()
    while True:
        time.sleep(12)
        print("command: {}\n".format(command.commandId))
        print(command.watchDog)
        command.executeCommand(command.commands.eg1)
        time.sleep(5)
