import socket 

from _thread import *
import threading

import time
import sys

import queue

import random

import string

SHIP_LENGTHS = (5, 4, 3, 3, 2)
NUM_SHIPS = len(SHIP_LENGTHS)

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
        # match ready [self/opponent]: confirmation that you/opponent is ready
        self.output_queue = queue.Queue()
        
        # TODO: Enter name
        self.name = "".join([random.choice(string.ascii_lowercase) for i in range(random.randint(3, 6))])

        # None if not in a match, Match object if in a match
        self.match = None
    
    # Input format: [keyword] [values...]
    # Possible keyword-value combinations:
    # chat [multi-space words]: send a message to chat
    # matchmake join: join matchmaking queue
    # matchmake leave: leave matchmaking queue
    # match [keyword] [args...] : described in Match
    def handle_input(self, client_input):
        split_input = client_input.split(" ")
        keyword = split_input[0]
        if keyword == "chat":
            chat_queue.put("{}: {}".format(self.name, " ".join(split_input[1:])))
        elif keyword == "matchmake":
            if self.match is None:
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
                    self.output_queue.put("error command {} not found".format(client_input))
            else:
                self.output_queue.put("error already in match")
        elif keyword == "match":
            if self.match is None:
                self.output_queue.put("error not in a match")
            else:
                self.match.input_queue.put((self, " ".join(split_input[1:])))
        else:
            self.output_queue.put("error keyword {} not found".format(keyword))

class Match:
    def __init__(self, p1, p2):
        # a queue of tuples (player, input message)
        # possible messages:
        # place [x1] [y1] [h/w] [x2] [y2] [h/w] ... NUM_SHIPS times - initialise the board.
        self.input_queue = queue.Queue()
        start_new_thread(self.handle_input, ())

        # game variables
        self.p1 = p1
        self.p2 = p2

        self.p1_board = Board()
        self.p2_board = Board()

        self.initialised_boards = 0
    
    def handle_input(self):
        while True:
            time.sleep(.1)
            while not self.input_queue.empty():
                player, input_message = self.input_queue.get()
                if player not in (self.p1, self.p2):
                    player.output_queue.put("error not authorised")
                split_input = input_message.split(" ")
                keyword = split_input[0]
                if keyword == "place":
                    if player == self.p1:
                        if len(split_input) < NUM_SHIPS * 3 + 1:
                            self.p1.output_queue.put("error place requires {} arguments".format(NUM_SHIPS * 3))
                        else:
                            if not self.p1_board.initialised:
                                try:
                                    func_in = [tuple(int(split_input[i]) if i % 3 != 0 else split_input[i] == 'h' for i in range(j, j+3)) for j in range(1, NUM_SHIPS * 3 + 1, 3)]
                                except:
                                    self.p1.output_queue.put("error cannot parse input")
                                result = self.p1_board.initialise(func_in)
                                if result:
                                    self.p1.output_queue.put("match ready self")
                                    self.p2.output_queue.put("match ready opponent")
                                else:
                                    self.p1.output_queue.put("error initialisation failed")
                            else:
                                self.p1.output_queue.put("error already initialised")
                    else:
                        if len(split_input) < NUM_SHIPS * 3 + 1:
                            self.p2.output_queue.put("error place requires {} arguments".format(NUM_SHIPS * 3))
                        else:
                            if not self.p2_board.initialised:
                                try:
                                    func_in = [tuple(int(split_input[i]) if i % 3 != 0 else split_input[i] == 'h' for i in range(j, j+3)) for j in range(1, NUM_SHIPS * 3 + 1, 3)]
                                except:
                                    self.p1.output_queue.put("error cannot parse input")
                                result = self.p2_board.initialise(func_in)
                                if result:
                                    self.p2.output_queue.put("match ready self")
                                    self.p1.output_queue.put("match ready opponent")
                                else:
                                    self.p2.output_queue.put("error initialisation failed")
                            else:
                                self.p2.output_queue.put("error already initialised")


# board class for player boards (0-indexed, row-first)
class Board:
    def __init__(self, height=9, width=13):
        self.height = height
        self.width = width
        self.board = None
        self.remaining_hidden = [i for i in SHIP_LENGTHS]
        self.remaining_ships = NUM_SHIPS
        self.initialised = False
    
    # orientations is a list of NUM_SHIPS tuples (x, y, rotation)
    # x, y are coords of top left
    # rotation is True for horizontal, False for vertical
    # returns boolean for success
    def initialise(self, ship_orientations):
        # init board
        self.board = [[Cell(self, i, j, -1, False) for j in range(self.width)] for i in range(self.height)]
        for i, (x, y, rotation) in enumerate(ship_orientations):
            ship_length = SHIP_LENGTHS[i]
            # check oob
            if x < 0 or y < 0 or (rotation and (x >= self.height or y > self.width - ship_length)) or (not rotation and (x > self.height - ship_length or y >= self.width)):
                return False
            if rotation:
                for j in range(y, y + ship_length):
                    # check if occupied
                    if self.board[x][j].boat != -1:
                        return False
                    self.board[x][j].boat = i
            else:
                for j in range(x, x + ship_length):
                    if self.board[j][y].boat != -1:
                        return False
                    self.board[j][y].boat = i
        self.initialised = True
        return True

# a cell in a board.
# boat:
# -1 for nothing
# 0 for 5-length
# 1 for 4-length
# 2 for 3-length
# 3 for 3-length
# 4 for 2-length
class Cell:
    def __init__(self, board, x, y, boat, hit):
        self.board = board
        self.x = x
        self.y = y
        self.boat = boat
        self.hit = hit

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
            p1.output_queue.put("matchmake match {}".format(p2.name))
            p2.output_queue.put("matchmake match {}".format(p1.name))
            m = Match(p1, p2)
            p1.match = m
            p2.match = m
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
    
    # p1 = Player()
    # p2 = Player()
    # m = Match(p1, p2)
    # p1.match = m
    # p2.match = m
    # m.input_queue.put((p1, "place 0 0 w 1 1 h 2 2 h 3 3 w 4 4 w"))
    # print(p1.output_queue.get())
    # while True:
    #     time.sleep(1)
