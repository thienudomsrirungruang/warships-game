import socket
import random

from _thread import *
import threading

import time

import sys

import msvcrt

import shutil # shutil.get_terminal_size()

from settings import *

import queue

# TODO: let server communicate this with client
SHIP_LENGTHS = (5, 4, 3, 3, 2)
NUM_SHIPS = len(SHIP_LENGTHS)

network_queue_lock = threading.Lock()
network_input_queue = queue.Queue()
network_output_queue = queue.Queue()

line_queue = queue.Queue()
current_line_lock = threading.Lock()
current_line = ""

chat_lock = threading.Lock()
chat_list = []

def send(sock):
    try:
        while True:
            network_queue_lock.acquire()
            while not network_output_queue.empty():
                message = network_output_queue.get()
                sock.send(message.encode('utf-8'))
            network_queue_lock.release()
            time.sleep(.1)
    except ConnectionError as e:
        print("ERROR: {}".format(e))
    sock.close()
    exit()

def receive(sock):
    # print("INFO: new thread started")
    while True:
        data = sock.recv(1024)
        network_queue_lock.acquire()
        network_input_queue.put(data.decode('utf-8'))
        network_queue_lock.release()

def start_client():
    match = None
    in_matchmaking = False
    while True:
        network_queue_lock.acquire()
        while not network_input_queue.empty():
            message = network_input_queue.get()
            split_input = message.split(" ")
            if split_input[0] == "chat":
                chat_lock.acquire()
                chat_list.append(" ".join(split_input[1:]))
                chat_lock.release()
            elif split_input[0] == "matchmake":
                if split_input[1] == "join":
                    in_matchmaking = True
                elif split_input[1] == "leave":
                    in_matchmaking = False
                elif split_input[2] == "match":
                    #TODO
                    pass
                else:
                    chat_list.append("WARN: incorrect command {}".format(message))
            else:
                chat_list.append("WARN: incorrect command {}".format(message))
        while not line_queue.empty():
            message = line_queue.get()
            network_output_queue.put("chat {}".format(message))
        network_queue_lock.release()


def listen_for_keypress():
    global current_line
    ignore_next = False
    while True:
        c = msvcrt.getwch()
        # if ignore_next:
        #     ignore_next = False
        #     continue
        print(ord(c))
        current_line_lock.acquire()
        if ord(c) >= 32 and ord(c) <= 126:
            current_line += c
        elif ord(c) in (0, 224):
            ignore_next = True
        elif ord(c) in (8, 127):
            if(len(current_line) > 0):
                current_line = current_line[:-1]
        elif ord(c) in (13,):
            line_queue.put(current_line)
            current_line = ""
        elif ord(c) in (3,):
            exit()
        # print(current_line)
        current_line_lock.release()

def main(server_ip, server_port):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((server_ip, server_port))
        start_new_thread(send, (sock,))
        start_new_thread(receive, (sock,))
        start_new_thread(listen_for_keypress, ())
    except ConnectionError as e:
        print("ERROR: {}".format(e))
        exit()
    while True:
        time.sleep(.1)

if __name__ == '__main__':
    main(SERVER_IP, SERVER_PORT)
