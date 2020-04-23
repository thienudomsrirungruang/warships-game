import socket 

from _thread import *
import threading

import time
import sys

import queue

import random

import string

# lock for the users dict to prevent race conditions
users_lock = threading.Lock()

# a dict of tuple(user_ip, user_port), Player
users = {}

# queue for chat messages
chat_queue = queue.Queue()

# matchmaking queue 
# TODO: implement better matchmaking (prevent duplicate matches within a reasonable time, etc.)
matchmaking_queue = []
matchmaking_queue_lock = threading.Lock()

class Player(object):
    def __init__(self):
        # No input queue - use the appropriate shared or game-specific input queue instead
        # Output format: [keyword] [values...]
        # Possible keyword-value combinations:
        # chat [multi-space words]: send a message to chat
        # matchmake join: matchmaking queue has been joined
        # matchmake leave: matchmaking queue has been left
        # matchmake match [name]: match has been found with [name]
        # error [message]: error
        self.output_queue = queue.Queue()
        
        # TODO: Enter name
        self.name = "".join([random.choice(string.ascii_lowercase) for i in range(random.randint(3, 6))])
    
    # Input format: [keyword] [values...]
    # Possible keyword-value combinations:
    # chat [multi-space words]: send a message to chat
    # matchmake join: join matchmaking queue
    # matchmake leave: leave matchmaking queue
    def handle_input(self, client_input):
        split_input = client_input.split(" ")
        keyword = split_input[0]
        if keyword == "chat":
            chat_queue.put("{}: {}".format(self.name, " ".join(split_input[1:])))
        elif keyword == "matchmake":
            # TODO: detect if in match
            if split_input[1] == "join":
                matchmaking_queue_lock.acquire()
                if self in matchmaking_queue:
                    self.output_queue.put("error already in matchmaking")
                else:
                    matchmaking_queue.append(self)
                    self.output_queue.put("matchmake join")
                matchmaking_queue_lock.release()
            elif split_input[1] == "leave":
                matchmaking_queue_lock.acquire()
                if self in matchmaking_queue:
                    matchmaking_queue.remove(self)
                    self.output_queue.put("matchmake leave")
                else:
                    self.output_queue.put("error not in matchmaking")
                matchmaking_queue_lock.release()
        else:
            self.output_queue.put("error keyword {} not found".format(keyword))

def handle_user_and_input(conn, addr):
    print("INFO: new thread started")
    users_lock.acquire()
    player = Player()
    users[(addr[0], addr[1])] = player
    users_lock.release()
    start_new_thread(handle_output, (conn, addr, player))
    chat_queue.put("{} has joined the game.".format(player.name))
    try:
        while True:
            data = conn.recv(1024)
            if data:
                data = data.decode("utf-8")
                print("INFO: data received from {}: {}".format(addr, data))
                users_lock.acquire()
                player.handle_input(data)
                users_lock.release()
                # conn.send(("hello world " + data).encode("utf-8"))
    except OSError:
        print("ERROR: Connection lost to {}".format(addr[0]))
    print("ERROR: Closed connection to {}".format(addr[0]))
    users_lock.acquire()
    del users[(addr[0], addr[1])]
    users_lock.release()
    chat_queue.put("{} has left the game.".format(player.name))
    matchmaking_queue_lock.acquire()
    if player in matchmaking_queue:
        matchmaking_queue.remove(player)
    matchmaking_queue_lock.release()
    conn.close()

def handle_output(conn, addr, player):
    try:
        while True:
            users_lock.acquire()
            if player.output_queue.empty():
                users_lock.release()
                time.sleep(.1)
                continue
            data = player.output_queue.get()
            users_lock.release()
            print("INFO: sending output to {}: {}".format(addr, data))
            conn.send(data.encode("utf-8"))
    except OSError:
        print("ERROR: Connection lost to {}".format(addr[0]))

# lobby for matchmaking
def lobby():
    while True:
        time.sleep(.1)
        matchmaking_queue_lock.acquire()
        while len(matchmaking_queue) >= 2:
            p1 = matchmaking_queue.pop(0)
            p2 = matchmaking_queue.pop(0)
            print("INFO: Match between {} and {}".format(p1.name, p2.name))
        matchmaking_queue_lock.release()
        
def handle_global_chat():
    # echo chat to all
    while True:
        time.sleep(.1)
        users_lock.acquire()
        while not chat_queue.empty():
            # print("hi?")
            data = chat_queue.get()
            # print("DEBUG: data = {}".format(data))
            msg = "chat {}".format(data)
            for player_to_send_to in users.values():
                # print("DEBUG: sending message {} to queue {}".format(msg, player_to_send_to))
                player_to_send_to.output_queue.put(msg)
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
    start_new_thread(handle_global_chat, ())


    while True:
        c, addr = sock.accept()

        print("INFO: Connected to {}:{}".format(addr[0], addr[1]))

        start_new_thread(handle_user_and_input, (c, addr))

if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else 5005
    main(port)
