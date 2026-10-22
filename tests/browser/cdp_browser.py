"""Minimal local Chrome DevTools client for dependency-free UI regression fixtures."""
import json
import os
import socket
import struct
from urllib.parse import urlsplit


class DevTools:
    def __init__(self, url):
        address = urlsplit(url)
        if address.hostname not in ('127.0.0.1', 'localhost'):
            raise ValueError('Only the disposable local browser is supported')
        self.socket = socket.create_connection((address.hostname, address.port), timeout=10)
        request = (f'GET {address.path} HTTP/1.1\r\nHost: {address.netloc}\r\n'
                   'Upgrade: websocket\r\nConnection: Upgrade\r\n'
                   'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n'
                   'Sec-WebSocket-Version: 13\r\nOrigin: http://localhost\r\n\r\n')
        self.socket.sendall(request.encode())
        header = b''
        while not header.endswith(b'\r\n\r\n'):
            header += self.read(1)
        if b' 101 ' not in header:
            raise RuntimeError(header.decode())
        self.sequence = 0

    def read(self, count):
        result = b''
        while len(result) < count:
            data = self.socket.recv(count - len(result))
            if not data:
                raise ConnectionError('Browser connection closed')
            result += data
        return result

    def call(self, method, params=None):
        self.sequence += 1
        payload = json.dumps({'id': self.sequence, 'method': method, 'params': params or {}}).encode()
        mask = os.urandom(4)
        length = len(payload)
        header = bytes([0x81, 0x80 | length]) if length < 126 else bytes([0x81, 0xfe]) + struct.pack('!H', length)
        self.socket.sendall(header + mask + bytes(value ^ mask[i % 4] for i, value in enumerate(payload)))
        message = b''
        while True:
            first, second = self.read(2)
            size = second & 127
            if size == 126:
                size = struct.unpack('!H', self.read(2))[0]
            elif size == 127:
                size = struct.unpack('!Q', self.read(8))[0]
            if size > 32 * 1024 * 1024:
                raise ValueError('Unexpectedly large browser frame')
            data = self.read(size)
            if first & 15 == 8:
                raise ConnectionError('Browser closed the session')
            message += data
            if not first & 0x80:
                continue
            response = json.loads(message)
            message = b''
            if response.get('id') == self.sequence:
                if 'error' in response:
                    raise RuntimeError(response['error'])
                return response.get('result', {})

    def close(self):
        self.socket.close()
