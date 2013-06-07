# BTPD client module
#
# Copyright 2013 Vaughan Kitchen <v.kitchen@gnoms.org>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

__doc__ = """btpy client module - A common interface to the btpd daemon.

Client(dir=/path/to/btpd/dir) - Class for creating btpd object
                                dir defaults to $HOME/.btpd

The following three functions support '-a' or torrent numbers
with the exception of drop() where '-a' is unsupported

They also return a list of error tuples for every torrent specified

Example usage: drop(0, 6, 54)

drop() - Remove torrents from btpd.

start() - Activate torrents.

stop() - Deactivate torrents.

Other Functions:

add() - Add torrents to btpd.

stat() - Get torrent stats from btpd.

get_data() - Return information on torrents.

"""

# Should socket stay open when we know a bunch of commands will be sent? btcli does this
# Untested with utf-8
import os
import socket
import struct
import binascii

errorCodes = ("success",
              "communication error",
              "bad content directory",
              "bad torrent",
              "bad torrent entry",
              "bad tracker",
              "couldn't create content directory",
              "no such key",
              "no such torrent entry",
              "btpd is shutting down",
              "torrent is active",
              "torrent entry exists",
              "torrent is inactive")

dataFormat = {'%#': 'number',
              '%n': 'title',
              '%t': 'state',
              '%d': 'dir',
              '%h': 'hash',
              '%P': 'peers',
              '%^': 'uprate',
              '%v': 'downrate',
              '%g': 'downed',
              '%u': 'uped',
              '%D': 'rec',
              '%U': 'sent',
              '%S': 'size',
              '%A': 'apieces',
              '%T': 'tpieces',
              '%H': 'hpieces'}

torState = ('I', '+', '-', 'L', 'S')

class Client():

    def __init__(self, dir='~/.btpd'):
        if dir.startswith('$HOME/'):
            self.dir = os.environ['HOME'] + dir[5:]
        elif dir.startswith('~/'):
            self.dir = os.environ['HOME'] + dir[1:]
        else:
            self.dir = dir
        self.decode = ['size','downed','peers','tpieces','apieces','hpieces', 'sent', 'rec', 'uprate']

    def _connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.dir + '/sock')

    def _close(self):
        self.sock.close()

    def _clear(self):
        self.data = lambda: None
        for key in dataFormat:
            setattr(self.data, dataFormat[key], [])

    def _send(self, message):
        self._connect()
        length = struct.pack('i', len(message))
        self.sock.send(length + message)

    def _recv(self):
        length = self.sock.recv(4)
        length = struct.unpack('i', length)[0]
        self.response = self.sock.recv(length)
        error = self._error(self.response)
        self._close()
        return error

    def _error(self, message):
        ## assume response type:  b'd4:codei'
        end = message.find(b'e', 8)
        code = int(message[8:end])
        return code, errorCodes[code]

    def _decode(self, message):
        ## assume ordinary list response format
        start = 18
        while True:
            start = message.find(b'li2ei', start) + 5
            end = message.find(b'ei2ei', start)
            self.data.number.append(message[start:end].decode('utf-8'))
            start = end + 5
            end = message.find(b'ei3e', start)
            self.data.state.append(message[start:end].decode('utf-8'))
            start = end + 4
            end = message.find(b':', start)
            length = int(message[start:end])
            start = end + 1
            self.data.title.append(message[start:start + length].decode('utf-8'))
            end = start + length + 5
            for x in range(0, 9):
                start = end + 5
                end = message.find(b'ei2ei', start)
                # self.decode is a list of commonly seperated data sent from btpd
                getattr(self.data, self.decode[x]).append(message[start:end].decode('utf-8'))
            start = end + 5
            end = message.find(b'ei1e20', start)
            self.data.downrate.append(message[start:end].decode('utf-8'))
            start = end + 7
            end = start + 20
            self.data.hash.append(binascii.hexlify(message[start:end]).decode('utf-8'))
            start = end + 3
            end = message.find(b':', start)
            length = int(message[start:end])
            start = end + 1
            self.data.dir.append(message[start:start + length].decode('utf-8'))
            start = start + length
            if message.find(b'eli', start) == -1:
                break

    def add(self, directory, torrent):
        """Add .torrent to btpd for download
        torrents are added as inactive, a number is returned for control

        directory = specifies folder in .btpd for download
        torrent = path to .torrent

        returns (errorCode, errorDefinition, torrentNumber)
        """
        message = b'l3:addd7:content'
        message += str(len(directory)).encode() + b':' + directory.encode()
        message += b'7:torrent'
        file_ = open(torrent, 'rb')
        data = file_.read()
        file_.close()
        message += str(len(data)).encode() + b':'
        self._send(message + data + b'ee')
        error = self._recv()
        start = self.response.find(b'numi', 11) + 4
        end = self.response.find(b'ee', start)
        return error[0], error[1], int(self.response[start:end])

    def drop(self, *torrents):
        if len(torrents) == 0:
            raise TypeError("drop() takes exactly 2 arguments (1 given)")
        elif not all(isinstance(x, int) for x in torrents):
            raise TypeError("drop() takes arguments of type 'int'")
        else:
            errors = []
            for number in torrents:
                message = b'l3:deli' + str(number).encode() + b'ee'
                self._send(message)
                errors.append(self._recv())
            return errors

    def start(self, *torrents):
        if len(torrents) == 0:
            raise TypeError("start() takes exactly 2 arguments (1 given)")
        elif '-a' in torrents:
            self._send(b'l9:start-alle')
        elif not all(isinstance(x, int) for x in torrents):
            raise TypeError("start() takes arguments '-a' or type 'int'")
        else:
            errors = []
            for number in torrents:
                message = b'l5:starti' + str(number).encode() + b'ee'
                self._send(message)
                errors.append(self._recv())
            return errors

    def stop(self, *torrents):
        if len(torrents) == 0:
            raise TypeError("stop() takes exactly 2 arguments (1 given)")
        elif '-a' in torrents:
            self._send(b'18:stop-alle')
        elif not all(isinstance(x, int) for x in torrents):
            raise TypeError("stop() takes arguments '-a' or type 'int'")
        else:
            errors = []
            for number in torrents:
                message = b'l4:stopi' + str(number).encode() + b'ee'
                self._send(message)
                errors.append(self._recv())
            return errors

    def stat(self):
        """Get list of data from btpd
        returns (errorCode, errorDefinition)

        To access the data use get_data()
        """
        self._clear()
        self._send(b'l4:tgetd4:fromi0e4:keysli4ei14ei3ei16ei1ei0ei7ei8ei9ei6ei13ei12ei11ei10ei5ei2eeee')
        error = self._recv()
        if self.response.find(b'li2', 18) != -1:
            self._decode(self.response)
        return error

    def get_data(self, *tables):
        """Used with the formatting characters of btcli
        returns a 2D list of the same order specified

        stat() is used to get the data from btpd. Please run it first

        The following is a list of the characters from `man btcli` with a few reductions:

               %n - torrent name
               %# - torrent number
               %h - torrent hash
               %d - download directory
               %t - state
               %P - peer count

               %^ - upload rate
               %v - download rate

               %D - downloaded bytes
               %U - uploaded bytes
               %g - bytes got
               %u - bytes uploaded
               %S - total size, in bytes

               %A - available pieces
               %T - total pieces
               %H - have pieces
        """
        response = []
        for x in tables:
            response.append(getattr(self.data, dataFormat[x]))
        return response
