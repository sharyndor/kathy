#!/usr/bin/python

from importlib.resources import is_resource
from queue import Queue
import select
import socket
from threading import Lock, Thread

from base64 import b64encode
from hashlib import sha1

from os import path, _exit

from time import sleep, time

PORT = 8080
VERSION = [0, 4, 0] # vMajor.Minor.Patch

class PolyConnection:
  def __init__(self, sock : socket):
    self.sock = sock
    self.buffer = bytes()
    self.should_continue = True
    self.thread = Thread(target=self.run, name='PolyConnection')
    self.squeue = Queue()
    self.rsock, self.ssock = socket.socketpair()
    self.process_data = self.determine_protocol

  def start(self):
    self.thread.start()
  
  def send(self, data):
    self.squeue.put(data)
    self.ssock.sendall(b'\1')

  def is_read_available(self):
    socks = [self.sock]
    rsocks, _, xsocks = select.select(socks, [], socks)

    if self.sock in xsocks: raise Exception("Socket failure (read)")

    return self.sock in rsocks
  
  def is_send_available(self):
    socks = [self.rsock]
    rsocks, _, xsocks = select.select(socks, [], socks)
    
    if self.rsock in xsocks: raise Exception("Socket failure (send)")

    return self.rsock in rsocks
  
  def send_all(self):
    while self.is_send_available():
      _ = self.rsock.recv(1)
      self.sock.sendall(self.squeue.get())

  def read_more(self):
    if self.is_read_available():
      self.buffer += self.sock.recv(1024)

  def read_some(self, n):
    while len(self.buffer) < n:
      self.read_more()

    result, self.buffer = self.buffer[:n], self.buffer[n:]
    return result

  def read8(self):
    return int.from_bytes(self.read_some(1), 'big')

  def read16(self):
    return int.from_bytes(self.read_some(2), 'big')

  def read32(self):
    return int.from_bytes(self.read_some(4), 'big')
    
  def read_until(self, ending):
    while ending not in self.buffer:
      self.read_more()

    n = self.buffer.find(ending) + len(ending)
    return self.read_some(n)

  def determine_protocol(self):
    pass

  def run(self):
    try:
      while self.should_continue:
        self.read_more()
        self.process_data()
        self.send_all()
        sleep(0.1)
    except Exception as e:
      self.should_continue = False
      self.sock.close()
      print(e)

    print('A socket has been closed. Disconnected?')

class PolyServer:
  def __init__(self, port):
    self.sockets = []
    self.lock = Lock()

    self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self.sock.bind(('', port))

  def accept_all(self):
    try:
      self.sock.listen(5)
      while True:
        sock, _ = self.sock.accept()
        websock = PolyConnection(sock)
        websock.start()
        with self.lock:
          self.sockets.append(websock)
    except:
      print('Accept socket died, I hope this is an auto-update...')

if __name__ == '__main__':
  print('Hello: v' + '.'.join([str(n) for n in VERSION]))
  server = PolyServer(PORT)
  server.start()
