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
        # name [name]: signals the player's name after joining/name change
        # matchmake join: matchmaking queue has been joined
        # matchmake leave: matchmaking queue has been left
        # matchmake match [name]: match has been found with [name]
        # error [message]: error
        # match ready [self/opponent]: confirmation that you/opponent is ready
        # match guess self [x] [y] [hit/miss] [num_ships]: after a guess, shows location, and whether it was successful or not.
        # match guess opponent [x] [y] [hit/miss] [num_ships]: after an opponent guess, shows location, and whether it was successful or not
        # match win [self/opponent]: signals a win
        # match leave [self/opponent]: signals the match has been left
        self.output_queue = queue.Queue()
        
        self.name = "".join([random.choice(string.ascii_lowercase) for i in range(random.randint(3, 6))])

        # None if not in a match, Match object if in a match
        self.match = None

        self.output_queue.put("name {}".format(self.name))
    
    # Input format: [keyword] [values...]
    # Possible keyword-value combinations:
    # chat [multi-space words]: send a message to chat
    # name [name]: change name
    # matchmake join: join matchmaking queue
    # matchmake leave: leave matchmaking queue
    # match [keyword] [args...] : described in Match
    def handle_input(self, client_input):
        split_input = client_input.split(" ")
        keyword = split_input[0]
        if keyword == "chat":
            chat_queue.put("{}: {}".format(self.name, " ".join(split_input[1:])))
        elif keyword == "name":
            if len(split_input) < 2:
                self.output_queue.put("error name requires 2 values")
            elif len(split_input[1]) == 0:
                self.output_queue.put("error please specify a name")
            else:
                old_name = self.name
                self.name = split_input[1]
                self.output_queue.put("name {}".format(self.name))
                chat_queue.put("{} has changed their name to {}".format(old_name, self.name))
        elif keyword == "matchmake":
            if self.match is None:
                if len(split_input) < 2:
                    self.output_queue.put("error matchmake requires 2 values")
                else:
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
        # guess [x] [y] - guess x, y.
        # leave - leave the match (and forfeit if the game is not over).
        self.input_queue = queue.Queue()
        
        # game variables
        self.p1 = p1
        self.p2 = p2

        self.in_game = {p1, p2}

        self.p1_board = Board()
        self.p2_board = Board()

        self.initialised_boards = 0
        self.turn = random.choice([p1, p2])
        self.game_ended = False

        start_new_thread(self.handle_input, ())

    def change_turn(self):
        if self.turn == self.p1:
            self.turn = self.p2
            self.output_to(self.p1, ("match turn opponent"))
            self.output_to(self.p2, ("match turn self"))
        else:
            self.turn = self.p1
            self.output_to(self.p1, ("match turn self"))
            self.output_to(self.p2, ("match turn opponent"))

    def leave_match(self, player):
        if player == self.p1:
            if self.p1 in self.in_game:
                self.p1.match = None
                self.output_to(self.p1, ("match leave self"))
                self.output_to(self.p2, ("match leave opponent"))
                self.in_game.remove(self.p1)
                if not self.game_ended:
                    self.output_to(self.p2, ("match win self"))
                    self.game_ended = True
            else:
                self.p1.output_queue.put("error not in this match")
        elif player == self.p2:
            if self.p2 in self.in_game:
                self.p2.match = None
                self.output_to(self.p2, ("match leave self"))
                self.output_to(self.p1, ("match leave opponent"))
                self.in_game.remove(self.p2)
                if not self.game_ended:
                    self.output_to(self.p1, ("match win self"))
                    self.game_ended = True
            else:
                self.p2.output_queue.put("error not in this match")

    def output_to(self, player, output):
        if player in self.in_game:
            player.output_queue.put(output)

    def handle_input(self):
        while True:
            time.sleep(.1)
            while not self.input_queue.empty():
                player, input_message = self.input_queue.get()
                if player not in (self.p1, self.p2):
                    self.output_to(player, ("error not authorised"))
                split_input = input_message.split(" ")
                keyword = split_input[0]
                if keyword == "place":
                    if self.game_ended:
                        self.output_to(player, ("error game has ended"))
                    elif player == self.p1:
                        if len(split_input) < NUM_SHIPS * 3 + 1:
                            self.output_to(self.p1, ("error place requires {} arguments".format(NUM_SHIPS * 3)))
                        else:
                            if not self.p1_board.initialised:
                                try:
                                    func_in = [tuple(int(split_input[i]) if i % 3 != 0 else split_input[i] == 'h' for i in range(j, j+3)) for j in range(1, NUM_SHIPS * 3 + 1, 3)]
                                except:
                                    self.output_to(self.p1, ("error cannot parse input"))
                                result = self.p1_board.initialise(func_in)
                                if result:
                                    self.output_to(self.p1, ("match ready self"))
                                    self.output_to(self.p2, ("match ready opponent"))
                                    self.initialised_boards += 1
                                    if self.initialised_boards == 2:
                                        self.change_turn()
                                else:
                                    self.output_to(self.p1, ("error initialisation failed"))
                            else:
                                self.output_to(self.p1, ("error already initialised"))
                    else:
                        if len(split_input) < NUM_SHIPS * 3 + 1:
                            self.output_to(self.p2, ("error place requires {} arguments".format(NUM_SHIPS * 3)))
                        else:
                            if not self.p2_board.initialised:
                                try:
                                    func_in = [tuple(int(split_input[i]) if i % 3 != 0 else split_input[i] == 'h' for i in range(j, j+3)) for j in range(1, NUM_SHIPS * 3 + 1, 3)]
                                except:
                                    self.output_to(self.p2, ("error cannot parse input"))
                                result = self.p2_board.initialise(func_in)
                                if result:
                                    self.output_to(self.p2, ("match ready self"))
                                    self.output_to(self.p1, ("match ready opponent"))
                                    self.initialised_boards += 1
                                    if self.initialised_boards == 2:
                                        self.change_turn()
                                else:
                                    self.output_to(self.p2, ("error initialisation failed"))
                            else:
                                self.output_to(self.p2, ("error already initialised"))
                elif keyword == "guess":
                    if len(split_input) < 3:
                        self.output_to(player, ("error guess requires 3 arguments"))
                    elif self.game_ended:
                        self.output_to(player, ("error game has ended"))
                    elif self.initialised_boards < 2:
                        self.output_to(player, ("error both players not ready yet"))
                    else:
                        try:
                            x = int(split_input[1])
                            y = int(split_input[2])
                            # oob
                            if x < 0 or y < 0 or x >= self.p1_board.height or y >= self.p1_board.width:
                                self.output_to(player, ("error out of bounds"))
                            elif player == self.p1:
                                if self.turn == self.p1:
                                    if self.p2_board.board[x][y].hit:
                                        self.output_to(self.p1, ("error already guessed"))
                                    else:
                                        is_boat, remaining_ships = self.p2_board.guess(x, y)
                                        self.output_to(self.p1, ("match guess self {} {} {} {}".format(x, y, "hit" if is_boat else "miss", remaining_ships)))
                                        self.output_to(self.p2, ("match guess opponent {} {} {} {}".format(x, y, "hit" if is_boat else "miss", remaining_ships)))
                                        if remaining_ships == 0:
                                            self.output_to(self.p1, ("match win self"))
                                            self.output_to(self.p2, ("match win opponent"))
                                            self.game_ended = True
                                        else:
                                            self.change_turn()
                                else:
                                    self.output_to(self.p1, ("error not player's turn"))
                            else: # player == self.p2
                                if self.turn == self.p2:
                                    if self.p1_board.board[x][y].hit:
                                        self.output_to(self.p2, ("error already guessed"))
                                    else:
                                        is_boat, remaining_ships = self.p1_board.guess(x, y)
                                        self.output_to(self.p2, ("match guess self {} {} {} {}".format(x, y, "hit" if is_boat else "miss", remaining_ships)))
                                        self.output_to(self.p1, ("match guess opponent {} {} {} {}".format(x, y, "hit" if is_boat else "miss", remaining_ships)))
                                        if remaining_ships == 0:
                                            self.output_to(self.p2, ("match win self"))
                                            self.output_to(self.p1, ("match win opponent"))
                                            self.game_ended = True
                                        else:
                                            self.change_turn()
                                else:
                                    self.output_to(self.p2, ("error not player's turn"))
                        except ValueError:
                            self.output_to(player, ("error cannot parse input"))
                elif keyword == "leave":
                    self.leave_match(player)
                else:
                    self.output_to(player, ("error command match {} not found".format(keyword)))

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
    
    def guess(self, x, y):
        if not self.board[x][y].hit:
            is_boat = False
            self.board[x][y].hit = True
            if self.board[x][y].boat != -1:
                is_boat = True
                boat = self.board[x][y].boat
                self.remaining_hidden[boat] -= 1
                if self.remaining_hidden[boat] <= 0:
                    self.remaining_ships -= 1
            return is_boat, self.remaining_ships

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
