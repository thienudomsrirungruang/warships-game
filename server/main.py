import socket 

from _thread import *
import threading

import time
import sys

import queue

users_lock = threading.Lock()

# a dict of tuple(user_ip, user_port), IOQueue
users = {}

class IOQueue(object):
    def __init__(self):
        self.input_queue = queue.Queue()
        self.output_queue = queue.Queue()

def handle_user_and_input(conn, addr):
    print("INFO: new thread started")
    users_lock.acquire()
    io_queue = IOQueue()
    users[(addr[0], addr[1])] = io_queue
    users_lock.release()
    start_new_thread(handle_output, (conn, addr, io_queue))
    try:
        while True:
            data = conn.recv(1024)
            if data:
                data = data.decode("utf-8")
                print("INFO: data received from {}: {}".format(addr, data))
                users_lock.acquire()
                io_queue.input_queue.put(data)
                users_lock.release()
                # conn.send(("hello world " + data).encode("utf-8"))
    except OSError:
        print("ERROR: Connection lost to {}".format(addr[0]))
    print("ERROR: Closed connection to {}".format(addr[0]))
    users_lock.acquire()
    del users[(conn, addr)]
    users_lock.release()
    conn.close()

def handle_output(conn, addr, io_queue):
    try:
        while True:
            users_lock.acquire()
            if io_queue.output_queue.empty():
                users_lock.release()
                time.sleep(.1)
                continue
            data = io_queue.output_queue.get()
            users_lock.release()
            print("INFO: sending output to {}: {}".format(addr, data))
            conn.send(data.encode("utf-8"))
    except OSError:
        print("ERROR: Connection lost to {}".format(addr[0]))

# lobby for matchmaking, and user communication
def lobby():
    #temp - echo chat to all
    while True:
        time.sleep(.1)
        users_lock.acquire()
        for user, io_queue in users.items():
            while not io_queue.input_queue.empty():
                # print("hi?")
                data = io_queue.input_queue.get()
                # print("DEBUG: data = {}".format(data))
                msg = str(user) +  " : " + data
                for send_to_io_queue in users.values():
                    # print("DEBUG: sending message {} to queue {}".format(msg, send_to_io_queue))
                    send_to_io_queue.output_queue.put(msg)
        users_lock.release()

def debug():
    while True:
        time.sleep(.5)
        print("DEBUG: users_lock = {}".format(users_lock.locked()))
        if not users_lock.locked():
            users_lock.acquire()
            print("DEBUG: users = {}".format(users))
            users_lock.release()

def main(port):
    
    # start_new_thread(debug, ())

    host = ""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((host, port))

    sock.listen(5)
    print("INFO: socket is now listening")

    start_new_thread(lobby,())


    while True:
        c, addr = sock.accept()

        print("INFO: Connected to {}:{}".format(addr[0], addr[1]))

        start_new_thread(handle_user_and_input, (c, addr))

if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else 5005
    main(port)
