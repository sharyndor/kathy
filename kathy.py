#!/usr/bin/python

from queue import Queue
import select
import socket
from threading import Lock, Thread

from base64 import b64encode
from hashlib import sha1

from http.client import HTTPSConnection
import json

from os import path, _exit

from time import sleep, time

import sys

PORT = 8080

class WebSocket:
  HANDSHAKE  = (
    b"HTTP/1.1 101 Switching Protocols\r\n"
    b"Upgrade: websocket\r\n"
    b"Connection: Upgrade\r\n"
    b"Sec-WebSocket-Accept: "
  )

  class Opcode:
    CONTINUATION = 0x0
    TEXT         = 0x1
    BINARY       = 0x2
    CLOSE        = 0x8
    PING         = 0x9
    PONG         = 0xA

  def __init__(self, sock : socket.socket):
    self.sock = sock
    self.buffer = bytes()
    self.should_continue = True
    self.messages = Queue()
    self.thread = Thread(target=self.run, name='WebSocket')
    self.squeue = Queue()
    self.rsock, self.ssock = socket.socketpair()
    self.backlog = []

  def start(self):
    self.thread.start()

  def read_more(self):
    socks = [self.sock, self.rsock]
    rsocks, _, _ = select.select(socks, [], socks)

    if self.sock in rsocks:
      self.buffer += self.sock.recv(1024)

    if self.rsock in rsocks:
      _ = self.rsock.recv(1)
      while not self.squeue.empty():
        self.sock.sendall(self.squeue.get())

  def read_some(self, n):
    while len(self.buffer) < n:
      self.read_more()

    result, self.buffer = self.buffer[:n], self.buffer[n:]
    return result
    
  def read_until(self, ending):
    while ending not in self.buffer:
      self.read_more()

    n = self.buffer.find(ending) + len(ending)
    result, self.buffer = self.buffer[:n], self.buffer[n:]
    return result

  def run(self):
    try:
      self.send_handshake(self.read_until(bytes(b'\r\n\r\n')))
      while self.should_continue:
        opcode, message = self.read_message()
        self.handle_message(opcode, message)
    except Exception as e:
      self.should_continue = False
      self.sock.close()
      print(e)

    print('A socket has been closed. Disconnected?')

  def send_handshake(self, request):
    nonce = request.split(b'Sec-WebSocket-Key: ')[1].split(b'\r\n')[0]
    static = b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
    key = b64encode(sha1(nonce + static).digest())
    response = WebSocket.HANDSHAKE + key + b'\r\n\r\n'
    self.squeue.put(response)
    self.ssock.sendall(b'\1')
    return None

  def read_message(self):
    header = self.read_some(2)

    # Opcode / Flags - 1 Byte
    opcode = (header[0] >> 0) & 0b1111
    #fin    = (header[0] >> 7) & 0b1
    #rsv1   = (header[0] >> 6) & 0b1
    #rsv2   = (header[0] >> 5) & 0b1
    #rsv3   = (header[0] >> 4) & 0b1

    # Mask / Length - 1 Byte
    length = (header[1] >> 0) & 0b1111111
    mask   = (header[1] >> 7) & 0b1

    # Extended Length - 2 Bytes
    if length == 126:
      header += self.read_some(2)
      length = int.from_bytes(header[2:4], 'big')
    # Extended Length - 8 bytes
    elif length == 127:
      header += self.read_some(8)
      length = int.from_bytes(header[2:10], 'big')

    # Mask - 4 Bytes
    mask_bytes = self.read_some(4) if mask else b'\0\0\0\0'

    # Payload - ? Bytes
    payload = bytes([b ^ mask_bytes[i % 4] for i, b in enumerate(self.read_some(length))])
    return opcode, payload

  def send_message(self, opcode, payload):
    header = bytes()

    # Opcode / Flags
    header += bytes([0x80 + opcode])

    # Mask / Length
    plen = len(payload)
    if plen < 126:
      header += bytes([plen])
    elif plen < 2**16:
      header += bytes([126])
      header += plen.to_bytes(2, 'big')
    elif plen < 2**64:
      header += bytes([127])
      header += plen.to_bytes(8, 'big')
    else:
      raise Exception

    # Mask Omitted

    # Payload
    self.squeue.put(header + payload)
    self.ssock.sendall(b'\1')

  def handle_message(self, opcode, payload):
    if opcode == WebSocket.Opcode.TEXT:
      message = payload.decode()
      self.messages.put(message)
    elif opcode == WebSocket.Opcode.PING:
      self.send_message(WebSocket.Opcode.PONG, payload)
    elif opcode == WebSocket.Opcode.CLOSE:
      self.send_message(WebSocket.Opcode.CLOSE, payload[0:2])
      self.sock.close()
      self.should_continue = False

class SocketHandler:
  sockets : list[WebSocket] = []

  def __init__(self, port):
    self.sockets = []
    self.lock = Lock()

    self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self.sock.bind(('', port))
    
  def start(self):
    Thread(target=self.accept_all, name='Accept').start()

    self.history = []

    # Run forever
    while True:
      with self.lock:
        # Get rid of any sockets which have stopped
        self.sockets = [sock for sock in self.sockets if sock.should_continue]

        if (select.select([sys.stdin], [], [], 0.0)[0]):
          serverMessage = input()
          for sock in self.sockets:
            self.send_logged_message(sock, {
              'sender' : 'Server',
              'text' : serverMessage,
            })

        for sock in self.sockets:
          while not sock.messages.empty():
            try:
              data = sock.messages.get()
              inMessage = json.loads(data)
            except:
              print('Weird data in: ' + data)
              continue

            self.process(sock, inMessage)
      sleep(0.1)

  def accept_all(self):
    try:
      self.sock.listen(5)
      while True:
        sock, _ = self.sock.accept()
        websock = WebSocket(sock)
        websock.start()
        with self.lock:
          self.sockets.append(websock)
    except:
      print('Accept socket died...')

  def process(self, sock, request) -> str:
    if request['type'] == 'connect':
      sock.sender = request['sender']
      self.send_image(sock)
      self.send_video(sock)
      self.send_message(sock, request)
      for message in self.history:
        self.send_message(sock, message)
    elif request['type'] == 'message':
      request['sender'] = sock.sender
      self.send_logged_message(sock, request)
    elif request['type'] == 'content':
      self.send_content(sock, request)

  def send_message(self, sock, message):
    sock.send_message(WebSocket.Opcode.TEXT, json.dumps(message).encode())

  def send_logged_message(self, sock, message):
    self.history.append(message)
    self.send_message(sock, message)
  
  def retrieve_content(self, id):
    data = []
    dataType = 'none'

    if id == 0:
      with open('image.jpg', 'rb') as f:
        data = b64encode(f.read()).decode('ascii')
        dataType = 'image/jpeg'
    else:
      with open('video.mp4', 'rb') as f:
        data = b64encode(f.read()).decode('ascii')
        dataType = 'video/mp4'

    return data, dataType

  def send_content(self, sock, id):
    data, dataType = self.retrieve_content(id)
    
    self.send_message(sock, {
      'sender' : 'server',
      'id' : id,
      'type' : 'content',
      'data' : data,
      'dataType' : dataType,
    })

  def send_image(self, sock):
    self.send_message(sock, {
      'sender' : 'server',
      'id' : 0,
      'type' : 'message',
      'dataType' : 'content',
    })
  
  def send_video(self, sock):
    self.send_message(sock, {
      'sender' : 'server',
      'id' : 2,
      'type' : 'message',
      'dataType' : 'content',
    })


if __name__ == '__main__':
  print('Hello world!')
  handler = SocketHandler(PORT)
  handler.start()
