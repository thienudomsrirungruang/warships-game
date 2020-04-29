import socket
import random

from _thread import *
import threading

import time

import sys

import shutil # shutil.get_terminal_size()

from settings import *

import queue

# TODO: let server communicate this with client
SHIP_LENGTHS = (5, 4, 3, 3, 2)
NUM_SHIPS = len(SHIP_LENGTHS)

input_queue_lock = threading.Lock()
input_queue = queue.Queue()

output_queue_lock = threading.Lock()
output_queue = queue.Queue()

def send(sock):
    try:
        while True:
            output_queue_lock.acquire()
            while not output_queue.empty():
                message = output_queue.get()
                sock.send(message.encode('utf-8'))
            output_queue_lock.release()
    except ConnectionError as e:
        print("ERROR: {}".format(e))
    sock.close()
    exit()

def receive(sock):
    # print("INFO: new thread started")
    while True:
        data = sock.recv(1024)
        input_queue_lock.acquire()
        input_queue.put(data)
        input_queue_lock.release()

def main(server_ip, server_port):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((server_ip, server_port))
        start_new_thread(send, (sock,))
        start_new_thread(receive, (sock,))
    except ConnectionError as e:
        print("ERROR: {}".format(e))
        exit()
    while True:
        time.sleep(.1)

if __name__ == '__main__':
    main(SERVER_IP, SERVER_PORT)
