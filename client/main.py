import socket
import random

import string
import re

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

MINIMUM_TERMINAL_SIZE = (90, 35)

allow_keypress = False

network_queue_lock = threading.Lock()
network_input_queue = queue.Queue()
network_output_queue = queue.Queue()

line_queue = queue.Queue()
current_line_lock = threading.Lock()
current_line = ""

need_redraw = threading.Event()
need_redraw.set()

chat_lock = threading.Lock()
chat_list = []

match = None

player_name = "Anonymous"

class Match:
    def __init__(self, opponent_name):
        self.opponent_name = opponent_name

        self.player_ready = False
        self.opponent_ready = False

        self.end = False

        self.width = 13
        self.height = 9

        self.is_turn = False

        self.placement_data = [None for _ in range(NUM_SHIPS)]

        self.player_board = Board(self.height, self.width)
        self.opponent_board = Board(self.height, self.width)

        self.player_ships_left = NUM_SHIPS
        self.opponent_ships_left = NUM_SHIPS

        self.match_chat = []
    
    def place(self, ship_id, coord_str, rotation):
        rotation = rotation.lower()
        coords = get_coords_from_string(coord_str, self.height, self.width)
        if coords is None:
            self.match_chat.append("Invalid coordinates.")
        elif self.placement_data[ship_id] is not None:
            self.match_chat.append("Ship already placed.")
        else:
            placement_data = ShipPlacementData(*coords, rotation[0])
            result = self.player_board.place_ship(ship_id, placement_data)
            if result:
                self.placement_data[ship_id] = placement_data
                self.match_chat.append("Ship successfully placed.")
            else:
                self.match_chat.append("Placement failed - check your coordinates again.")
    
    def ready(self, is_self):
        if is_self:
            self.player_ready = True
            self.match_chat.append("You are ready!")
        else:
            self.opponent_ready = True
            self.match_chat.append("Your opponent is ready!")
        need_redraw.set()

    def set_turn(self, is_turn):
        if is_turn:
            self.match_chat.append("It is now your turn!")
        else:
            self.match_chat.append("It is now your opponent's turn!")
        self.is_turn = is_turn
        need_redraw.set()

    def confirm_self_guess(self, x, y, is_hit, remaining_ships):
        self.opponent_board.board[x][y].boat = bool(is_hit)
        self.opponent_board.board[x][y].hit = True
        self.player_ships_left = remaining_ships
        self.match_chat.append("Your guess at {} has {}!".format(get_string_from_coords(x, y, self.height, self.width), "hit" if is_hit else "missed"))
        need_redraw.set()

    def confirm_opponent_guess(self, x, y, is_hit, remaining_ships):
        self.player_board.board[x][y].hit = True
        self.opponent_ships_left = remaining_ships
        self.match_chat.append("Your opponent's guess at {} has {}!".format(get_string_from_coords(x, y, self.height, self.width), "hit" if is_hit else "missed"))
        need_redraw.set()

    def win(self, is_self):
        self.match_chat.append("You have {} the match!".format("won" if is_self else "lost"))
        self.match_chat.append("The match is now over. Use '/match leave' to leave the match.")
        self.end = True
        need_redraw.set()

    def opponent_leave(self):
        self.match_chat.append("Your opponent has left the match.")
        need_redraw.set()

    def handle_input(self, input_line):
        if self.end:
            self.match_chat.append("The game has ended. Please use '/match leave' to leave the game.")
        elif not self.player_ready:
            split_input = input_line.split(" ")
            if split_input[0] == "confirm":
                if self.placement_data.count(None) > 0:
                    self.match_chat.append("Please place all your ships before confirming.")
                else:
                    network_queue_lock.acquire()
                    network_output_queue.put("match place {}".format(" ".join(map(str, self.placement_data))))
                    network_queue_lock.release()
            elif len(split_input) < 3:
                self.match_chat.append("Please either type \'confirm\' or a placement described above.")
            else:
                if split_input[0].lower() in list(string.ascii_lowercase[:NUM_SHIPS]) and split_input[2] in ("horizontal", "vertical", "h", "v"):
                    self.place(string.ascii_lowercase.index(split_input[0].lower()), split_input[1], split_input[2])
                else:
                    self.match_chat.append("Invalid placement.")
        elif self.player_ready and self.opponent_ready:
            if self.is_turn:
                guess = get_coords_from_string(input_line, self.height, self.width)
                if guess is None:
                    self.match_chat.append("Invalid guess. Please try again.")
                else:
                    if self.opponent_board.board[guess[0]][guess[1]].hit:
                        self.match_chat.append("You have already guessed this square. Please try again.")
                    else:
                        network_queue_lock.acquire()
                        network_output_queue.put("match guess {} {}".format(guess[0], guess[1]))
                        network_queue_lock.release()
            else:
                self.match_chat.append("Please wait until it is your turn.")
        else:
            self.match_chat.append("Please wait for your opponent to be ready.")
        need_redraw.set()
    
    # returns a 30-ishx59 string corresponding to the game window.
    def get_string(self, width=59, height=29):
        global player_name
        # draws a window, which is then drawn to the screen.
        window = [[" "] * width for _ in range(height)]
        names = ("{0:<" + str(width // 2) + "} {1:>" + str(width // 2) + "}\n").format(\
                    player_name if len(player_name) <= width // 2 else player_name[:width // 2], \
                    self.opponent_name if len(self.opponent_name) <= width // 2 else self.opponent_name[:width // 2])
        draw(window, height, width, 0, 1, 0, width, names, textwrap="n")
        if self.player_ready and self.opponent_ready:
            player_ships_left = "o" * self.player_ships_left + "x" * (NUM_SHIPS - self.player_ships_left)
            opponent_ships_left = "x" * (NUM_SHIPS - self.opponent_ships_left) + "o" * self.opponent_ships_left
            ships_left_line = ("{0:<" + str(width // 2) + "} {1:>" + str(width // 2) + "}\n").format(player_ships_left, opponent_ships_left)
            draw(window, height, width, 1, 1, 0, width, ships_left_line, textwrap="n")
            if self.is_turn:
                draw(window, height, width, 2, 1, 0, width, "Your turn", textwrap="n", alignh="l")
            else:
                draw(window, height, width, 2, 1, 0, width, "Opponent's turn", textwrap="n", alignh="r")
        else:
            context_line = ("{0:<" + str(width // 2) + "} {1:>" + str(width // 2) + "}\n").format(\
                        "Ready" if self.player_ready else "Not ready", "Ready" if self.opponent_ready else "Not ready")
            draw(window, height, width, 1, 1, 0, width, context_line, textwrap="n")
        self_board_string = self.player_board.get_board_string(True, lpadding=0, rpadding=0)
        draw(window, height, width, 3, self.height + 1, 1, self.width * 2 + 1, self_board_string, textwrap="n")
        opponent_board_string = self.opponent_board.get_board_string(False, lpadding=0, rpadding=0)
        draw(window, height, width, 3, self.height + 1, self.width * 2 + 4, self.width * 2 + 1, opponent_board_string, textwrap="n")
        if self.player_ready and self.opponent_ready:
            explain_text = "Both players are ready, so the guessing phase begins! When it is your turn, write down a square. You'll see if it was a hit or a miss. A ship is sunk if all of its squares are hit! Be the first to sink your opponent's ships to win.\nTurn indicators can be found at the top. The number of o-s below your name represent how many ships you have yet to sink.\nAn x means that square hit something, an o means it missed.\nDon't forget, you're attacking the right-side grid and your opponent is attacking the left side."
            draw(window, height, width, self.height + 5, height - self.height - 5, 1, width - 2, explain_text)
        else:
            draw(window, height, width, self.height + 5, NUM_SHIPS + 4, 2, 26, self.get_placement_table(), textwrap="n")
            explain_text = "Welcome to Warships! You are on the left, and your opponent is on the right. Please place your ships on your board on the left, while your opponent places theirs. The box on the bottom is the match chat."
            draw(window, height, width, self.height + 5, 9, 30, width - 31, explain_text)
            command_explain_text = "To place a ship, specify the letter, top left corner, and direction. For example, if you want to place ship B horizontally with top left corner B4, type:\nB B4 horizontal\nOther examples: c c2 vertical, E L1 v\nOnce you're done, type 'confirm' to ready up."
            draw(window, height, width, self.height + 14, height - self.height - 14, 1, width - 2, command_explain_text)
        return "\n".join(["".join(_) for _ in window])

    # just for output: (NUM_SHIPS + 4) * 26
    def get_placement_table(self):
        out = ""
        out += "|------|--------|--------|\n"
        out += "| Ship | Length | Placed |\n"
        out += "|------|--------|--------|\n"
        for i in range(NUM_SHIPS):
            out += "|{0:^6}|{1:^8}|{2:^8}|\n".format(string.ascii_uppercase[i], SHIP_LENGTHS[i], "No" if self.placement_data[i] is None else "Yes")
        out += "|------|--------|--------|"
        return out

class ShipPlacementData:
    def __init__(self, x, y, rotation):
        self.x = x
        self.y = y
        self.rotation = rotation
    
    def __str__(self):
        return "{} {} {}".format(self.x, self.y, self.rotation)


class Board:
    def __init__(self, height=9, width=13):
        self.height = height
        self.width = width
        self.remaining_ships = NUM_SHIPS
        self.board = [[Cell(self, i, j, -1, False) for j in range(self.width)] for i in range(self.height)]
        self.initialised = False
        
    # semi-recycled from server code
    def place_ship(self, number, ship_placement_data):
        ship_length = SHIP_LENGTHS[number]
        x = ship_placement_data.x
        y = ship_placement_data.y
        rotation = ship_placement_data.rotation == "h"
        # check oob
        if x < 0 or y < 0 or (rotation and (x >= self.height or y > self.width - ship_length)) or (not rotation and (x > self.height - ship_length or y >= self.width)):
            return False
        if rotation:
            for j in range(y, y + ship_length):
                # check if occupied
                if self.board[x][j].boat != -1:
                    return False
            for j in range(y, y + ship_length):
                self.board[x][j].boat = number
        else:
            for j in range(x, x + ship_length):
                if self.board[j][y].boat != -1:
                    return False
            for j in range(x, x + ship_length):
                self.board[j][y].boat = number
        return True

    def get_board_string(self, is_self, show_coords=True, show_types=True, hitmarker="x", missmarker="o", unknownmarker=".", padding=" ", hspacing=1, vspacing=0, lpadding=1, rpadding=1):
        out = ""
        width = (2 if show_coords else 0) + self.width + (self.width - 1) * hspacing + lpadding + rpadding
        for i in range(self.height):
            row_number = self.height - i
            row = " " * (lpadding - len(str(row_number)) + 1 if show_types else lpadding)
            if show_coords:
                row += str(row_number) + " " * hspacing
            for j in range(self.width):
                cell = self.board[i][j]
                if is_self:
                    if cell.hit:
                        if cell.boat != -1:
                            row += hitmarker
                        else: # no boat
                            row += missmarker
                    else:
                        if show_types and cell.boat != -1:
                            row += string.ascii_uppercase[cell.boat]
                        else:
                            row += unknownmarker
                else: # opponent board
                    if cell.boat == -1:
                        row += unknownmarker
                    elif cell.boat == 0:
                        row += missmarker
                    else: # == 1
                        row += hitmarker
                # add spacing if needed
                if j != self.width - 1:
                    row += " " * hspacing
            row += " " * rpadding
            out += row + "\n"
            #add padding if needed
            if i != self.height - 1:
                for j in range(vspacing):
                    out += " " * width + "\n"
        if show_coords:
            out += " " * (lpadding + 1)
            for i in range(self.width):
                out += " " * hspacing
                out += string.ascii_lowercase[i]
        return out

# hit:
# for player's board, -1 for no boat, others for index
# for opponent's board, -1 for unknown, 0 for miss, 1 for hit
class Cell:
    def __init__(self, board, x, y, boat, hit):
        self.board = board
        self.x = x
        self.y = y
        self.boat = boat
        self.hit = hit


# Gets coords from <letter><number>. A1 is bottom left or (0, (height)-1).
# Chess order, so ABC... are columns and 123... are rows.
# Returns None if validation fails.
def get_coords_from_string(s, height, width):
    s = s.lower()
    if not re.fullmatch(r"[a-z]\d+", s):
        return None
    x = height - int(s[1:])
    y = string.ascii_lowercase.index(s[0])
    if 0 <= x < height and 0 <= y < width:
        return x, y
    return None

# inverse of get_coords_from_string. No validation.
def get_string_from_coords(x, y, height, width):
    return string.ascii_uppercase[y] + str(height - x)

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

def add_to_chat(message):
    chat_lock.acquire()
    chat_list.append(message)
    chat_lock.release()
    need_redraw.set()

def start_client():
    global match
    global player_name
    in_matchmaking = False
    while True:
        network_queue_lock.acquire()
        while not network_input_queue.empty():
            message = network_input_queue.get()
            split_input = message.split(" ")
            if split_input[0] == "chat":
                add_to_chat(" ".join(split_input[1:]))
            elif split_input[0] == "matchmake":
                if split_input[1] == "join":
                    add_to_chat("Successfully joined matchmaking.")
                    in_matchmaking = True
                elif split_input[1] == "leave":
                    add_to_chat("Successfully left matchmaking.")
                    in_matchmaking = False
                elif split_input[1] == "match":
                    in_matchmaking = False
                    add_to_chat("A match has been found with {}".format(split_input[2]))
                    match = Match(split_input[2])
                else:
                    add_to_chat("WARN: incorrect command {}".format(message))
            elif split_input[0] == "name":
                player_name = split_input[1]
            elif split_input[0] == "match":
                if match is None:
                    add_to_chat("WARN: Match command recieved without a match: {} - ignoring".format(message))
                else:
                    if split_input[1] == "ready":
                        match.ready(split_input[2] == "self")
                    elif split_input[1] == "turn":
                        match.set_turn(split_input[2] == "self")
                    elif split_input[1] == "guess":
                        if split_input[2] == "self":
                            match.confirm_self_guess(int(split_input[3]), int(split_input[4]), split_input[5] == "hit", int(split_input[6]))
                        else: # opponent
                            match.confirm_opponent_guess(int(split_input[3]), int(split_input[4]), split_input[5] == "hit", int(split_input[6]))
                    elif split_input[1] == "win":
                        match.win(split_input[2] == "self")
                    elif split_input[1] == "leave":
                        if split_input[2] == "self":
                            add_to_chat("Successfully left the match.")
                            match = None
                        else:
                            match.opponent_leave()
                    else:
                        add_to_chat("WARN: incorrect command {}".format(message))
            elif split_input[0] == "error":
                add_to_chat("WARN: Error received from server: {}".format(message))
            else:
                add_to_chat("WARN: incorrect command {}".format(message))
        while not line_queue.empty():
            message = line_queue.get()
            if message.startswith("/"):
                split_input = message.split(" ")
                keyword = split_input[0][1:]
                if keyword == "help":
                    add_to_chat("""/help - shows this message.
/matchmake <join/leave> - joins or leaves matchmaking.
/name <name> - changes your name.
/match leave - leaves the match, if there is one going on.
/chat <message> - chat when in a match.""")
                elif keyword == "matchmake":
                    if len(split_input) < 2:
                        add_to_chat("Usage: /matchmake <join/leave>")
                    elif split_input[1] == "join":
                        if not in_matchmaking and match is None:
                            network_output_queue.put("matchmake join")
                        else:
                            add_to_chat("You are already in matchmaking, or in a match!")
                    elif split_input[1] == "leave":
                        if in_matchmaking:
                            network_output_queue.put("matchmake leave")
                        else:
                            add_to_chat("You are not in matchmaking!")
                # TODO: can only be done when not in match/matchmaking
                elif keyword == "name":
                    if len(split_input) < 2:
                        add_to_chat("Usage: /name <new name>")
                    elif split_input[1] == "":
                        add_to_chat("Usage: /name <new name>")
                    else:
                        network_output_queue.put("name {}".format(split_input[1]))
                elif keyword == "match":
                    if match is None:
                        add_to_chat("You are not in a match.")
                    elif len(split_input) < 2:
                        add_to_chat("Usage: /match leave")
                    elif split_input[1] == "leave":
                        network_output_queue.put("match leave")
                    else:
                        add_to_chat("Usage: /match leave")
                elif keyword == "chat":
                    if len(split_input) < 2:
                        add_to_chat("Usage: /chat <message>")
                    elif split_input[1] == "":
                        add_to_chat("Usage: /chat <message>")
                    else:
                        if match is None:
                            network_output_queue.put("chat {}".format(" ".join(split_input[1:])))
                        else:
                            add_to_chat("You cannot change your name in a match!")
                else:
                    add_to_chat("Command not found.")
            else:
                if match is None:
                    if len(message) > 0:
                        network_output_queue.put("chat {}".format(message))
                else:
                    network_queue_lock.release()
                    match.handle_input(message)
                    network_queue_lock.acquire()
        network_queue_lock.release()
        time.sleep(.1)

def redraw():
    global current_line
    global allow_keypress
    while True:
        if need_redraw.is_set():
            need_redraw.clear()
            term_size = shutil.get_terminal_size()
            lines = term_size.lines
            columns = term_size.columns - 1
            screen = [["."] * columns for _ in range(lines)]
            # draw(screen, lines, columns, 2, lines - 4, 5, columns - 10, """Lorem \nipsum \ndolor sit amet, \nconsectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Morbi tristique senectus et netus. Eget dolor morbi non arcu. Cras pulvinar mattis nunc sed blandit libero volutpat sed. A iaculis at erat pellentesque adipiscing commodo elit at. Suspendisse ultrices gravida dictum fusce ut placerat orci. Sit amet justo donec enim. Parturient montes nascetur ridiculus mus mauris. Vestibulum morbi blandit cursus risus at ultrices. At in tellus integer feugiat scelerisque varius morbi enim nunc."""\
            #                                                         , alignh="r", alignv="m", padding=" ", textwrap="w")
            if lines < MINIMUM_TERMINAL_SIZE[1] or columns < MINIMUM_TERMINAL_SIZE[0]:
                allow_keypress = False
                message = "Your terminal is too small to display the game! Please resize it.\nMinimum size: ({}, {})\nCurrent size: ({}, {})".format(MINIMUM_TERMINAL_SIZE[1], MINIMUM_TERMINAL_SIZE[0], lines, columns)
                draw(screen, lines, columns, 0, lines, 0, columns, message, alignh="m", alignv="m", textwrap="w")
            else:
                allow_keypress = True
                current_line_lock.acquire()
                draw(screen, lines, columns, lines - 1, 1, 0, columns, current_line, alignh="l", textwrap="n", anchor="r")
                current_line_lock.release()
                chat_lock.acquire()
                draw(screen, lines, columns, 0, lines - 1, 60, columns - 60, "\n".join(chat_list), alignv="b")
                chat_lock.release()
                if match is not None:
                    draw(screen, lines, columns, 0, 29, 0, 59, match.get_string(), textwrap="n")
                    draw(screen, lines, columns, 30, lines - 31, 0, 59, "\n".join(match.match_chat), alignv="b")
                else:
                    message = "Welcome to Warships!\nType anything to chat on the right.\n/matchmake join to join a match\n/name <name> to change your name\n/help for other commands"
                    draw(screen, lines, columns, 1, lines - 3, 2, 59-4, message, alignh="l", alignv="m", textwrap="w")
            sys.stdout.write("\n" + "\n".join(["".join(_) for _ in screen]))
            time.sleep(.03)
            # current_line_lock.acquire()
            # print("hi")
            # sys.stdout.write("{}\n".format(current_line))
            # current_line_lock.release()

# alignh : "l" for left, "m" for middle, "r" for right
# alignv : "t" for top, "m" for middle, "b" for bottom
# textwrap: "n" for none, "w" for words, "g" for greedy
# anchor: "l" for left, "r" for right
def draw(screen, lines, columns, startl, numl, startc, numc, content, alignh="l", alignv="t", padding=" ", textwrap="w", anchor="l"):
    subscreen = [[padding] * numc for _ in range(numl)]
    # reverse
    if anchor == "r":
        content = content[::-1]
        if alignh == "l": alignh = "r"
        elif alignh == "r": alignh = "l"
        if alignv == "t": alignv = "b"
        elif alignv == "b": alignv = "t"
    text_lines = content.splitlines()
    if textwrap == "n":
        new_lines = []
        for line in text_lines:
            if len(line) > numc:
                new_lines.append(line[:numc])
            else:
                new_lines.append(line)
        text_lines = new_lines
    elif textwrap == "g":
        new_lines = []
        for line in text_lines:
            while True:
                if(len(line) <= numc):
                    new_lines.append(line)
                    break
                new_lines.append(line[:numc])
                line = line[numc:]
        text_lines = new_lines
    elif textwrap == "w":
        new_lines = []
        for line in text_lines:
            current_line = ""
            words = iter(line.split(" "))
            word = next(words, None)
            while word is not None:
                # check new length of line
                if len(word) == 0:
                    word = next(words, None)
                elif len(word) + len(current_line) + (1 if len(current_line) > 0 else 0) <= numc:
                    if len(current_line) == 0:
                        current_line += word
                    else:
                        current_line += " " + word
                    word = next(words, None)
                elif len(word) > numc:
                    cut_length = numc - len(current_line) - (1 if len(current_line) > 0 else 0)
                    if cut_length > 0:
                        if len(current_line) == 0:
                            current_line += word[:cut_length]
                        else:
                            current_line += " " + word[:cut_length]
                        word = word[cut_length:]
                    else:
                        new_lines.append(current_line)
                        current_line = ""
                else:
                    new_lines.append(current_line)
                    current_line = ""
            if len(current_line) > 0:
                new_lines.append(current_line)
        text_lines = new_lines
    num_lines = len(text_lines)
    if num_lines >= numl:
        if alignv == "m":
            text_lines = text_lines[(num_lines - numl) // 2, (num_lines - numl) // 2 + numl]
        elif alignv == "b":
            text_lines = text_lines[-numl:]
        first_line = 0
    elif alignv == "t":
        first_line = 0
    elif alignv == "m":
        first_line = (numl - num_lines) // 2
    else:
        first_line = numl - num_lines
    for i in range(min(num_lines, numl)):
        if alignh == "l":
            first_col = 0
        elif alignh == "m":
            first_col = (numc - len(text_lines[i])) // 2
        else:
            first_col = numc - len(text_lines[i])
        for j in range(len(text_lines[i])):
            # print(first_line + i, first_col + j)
            subscreen[first_line + i][first_col + j] = text_lines[i][j]
    # reverse back
    if anchor == "r":
        new_subscreen = []
        for line in subscreen[::-1]:
            new_subscreen.append(line[::-1])
        subscreen = new_subscreen
    # transfer to screen
    for line in range(numl):
        for col in range(numc):
            screen[startl + line][startc + col] = subscreen[line][col]


def listen_for_keypress():
    global current_line
    global allow_keypress
    ignore_next = False
    while True:
        c = msvcrt.getwch()
        if not allow_keypress:
            continue
        if ignore_next:
            ignore_next = False
            continue
        current_line_lock.acquire()
        if ord(c) >= 32 and ord(c) <= 126:
            current_line += c
            need_redraw.set()
        elif ord(c) in (0, 224):
            ignore_next = True
        elif ord(c) in (8, 127):
            if(len(current_line) > 0):
                current_line = current_line[:-1]
                need_redraw.set()
        elif ord(c) in (13,):
            line_queue.put(current_line)
            current_line = ""
            need_redraw.set()
        elif ord(c) in (3,):
            exit()
        current_line_lock.release()

def check_for_resize():
    term_size = shutil.get_terminal_size()
    while True:
        new_term_size = shutil.get_terminal_size()
        if new_term_size != term_size:
            term_size = new_term_size
            need_redraw.set()
        time.sleep(.03)

def main(server_ip, server_port):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((server_ip, server_port))
        start_new_thread(send, (sock,))
        start_new_thread(receive, (sock,))
        start_new_thread(listen_for_keypress, ())
        start_new_thread(check_for_resize, ())
        start_new_thread(redraw, ())
        start_new_thread(start_client, ())
    except ConnectionError as e:
        print("ERROR: {}".format(e))
        exit()
    while True:
        time.sleep(.1)

if __name__ == '__main__':
    main(SERVER_IP, SERVER_PORT)
