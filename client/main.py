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

network_queue_lock = threading.Lock()
network_input_queue = queue.Queue()
network_output_queue = queue.Queue()

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
                    print("WARN: incorrect command {}".format(message))
            else:
                print("WARN: incorrect command {}".format(message))
        network_queue_lock.release()

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
