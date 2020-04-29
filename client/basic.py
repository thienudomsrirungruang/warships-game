import socket
import random

from _thread import *
import threading

import time

import sys

import shutil # shutil.get_terminal_size()

from settings import *

move_up_next = False

def main(server_ip, server_port):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((server_ip, server_port))
        start_new_thread(send, (sock,))
    except ConnectionError as e:
        print("ERROR: {}".format(e))
        exit()
    while True:
        time.sleep(.1)

def send(sock):
    try:
        start_new_thread(receive, (sock,))

        while True:
            message = sys.stdin.readline().strip()
            move_up_next = True
            sock.send(message.encode('utf-8'))
        sock.close()
    except ConnectionError as e:
        print("ERROR: {}".format(e))
    exit()

def receive(sock):
    # print("INFO: new thread started")
    while True:
        data = sock.recv(1024)
        if move_up_next:
            sys.stdout.write("\r\033[A{}\n>> ".format(data.decode('utf-8')))
        else:
            sys.stdout.write("\r{}\n>> ".format(data.decode('utf-8')))

if __name__ == '__main__':
    main(SERVER_IP, SERVER_PORT)
