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
        elif rotation not in ("horizontal", "vertical"):
            self.match_chat.append("Rotation should either be horizontal or vertical.")
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
    
    def handle_input(self, input_line):
        if not self.player_board.initialised:
            split_input = input_line.split(" ")
            if split_input[0] == "confirm":
                # TODO
                pass
            elif len(split_input) < 3:
                self.match_chat.append("Please either type \'confirm\' or a placement described above.")
            else:
                if split_input[0].isdigit() and split_input[2] in ("horizontal", "vertical"):
                    self.place(int(split_input[0]), split_input[1], split_input[2])
                else:
                    self.match_chat.append("Invalid placement.")
        else:
            # TODO
            pass
        need_redraw.set()
    
    # returns a 30-ishx29 string corresponding to the game window.
    def get_string(self, width=29):
        global player_name
        out = ""
        out += ("{0:<" + str(width // 2) + "} {1:>" + str(width // 2) + "}\n").format(\
                    player_name if len(player_name) <= width // 2 else player_name[:width // 2], \
                    self.opponent_name if len(self.opponent_name) <= width // 2 else self.opponent_name[:width // 2])
        out += " " * width + "\n" # TODO: hit counters
        out += self.player_board.get_board_string(True)
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
                    if cell.hit == -1:
                        row += unknownmarker
                    elif cell.hit == 0:
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
def get_coords_from_string(s, height, width):
    s = s.lower()
    if not re.fullmatch(r"[a-z]\d+", s):
        return None
    x = height - int(s[1:])
    y = string.ascii_lowercase.index(s[0])
    if 0 <= x < height and 0 <= y < width:
        return x, y
    return None

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
                    add_to_chat("A match has been found with {}".format(split_input[2]))
                    match = Match(split_input[2])
                else:
                    add_to_chat("WARN: incorrect command {}".format(message))
            elif split_input[0] == "name":
                player_name = split_input[1]
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
/name <name> - changes your name.""")
                elif keyword == "matchmake":
                    if len(split_input) < 2:
                        add_to_chat("Usage: /matchmake <join/leave>")
                    elif split_input[1] == "join":
                        if not in_matchmaking:
                            network_output_queue.put("matchmake join")
                        else:
                            add_to_chat("You are already in matchmaking!")
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
                else:
                    add_to_chat("Command not found.")
            else:
                if match is None:
                    network_output_queue.put("chat {}".format(message))
                else:
                    match.handle_input(message)
        network_queue_lock.release()
        time.sleep(.1)

def redraw():
    global current_line
    while True:
        if need_redraw.is_set():
            need_redraw.clear()
            term_size = shutil.get_terminal_size()
            lines = term_size.lines
            columns = term_size.columns - 1
            screen = [["."] * columns for _ in range(lines)]
            # draw(screen, lines, columns, 2, lines - 4, 5, columns - 10, """Lorem \nipsum \ndolor sit amet, \nconsectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Morbi tristique senectus et netus. Eget dolor morbi non arcu. Cras pulvinar mattis nunc sed blandit libero volutpat sed. A iaculis at erat pellentesque adipiscing commodo elit at. Suspendisse ultrices gravida dictum fusce ut placerat orci. Sit amet justo donec enim. Parturient montes nascetur ridiculus mus mauris. Vestibulum morbi blandit cursus risus at ultrices. At in tellus integer feugiat scelerisque varius morbi enim nunc."""\
            #                                                         , alignh="r", alignv="m", padding=" ", textwrap="w")
            current_line_lock.acquire()
            draw(screen, lines, columns, lines - 1, 1, 0, columns, current_line, alignh="l", textwrap="n", anchor="r")
            current_line_lock.release()
            chat_lock.acquire()
            draw(screen, lines, columns, 0, lines - 1, 60, columns - 60, "\n".join(chat_list), alignv="b")
            chat_lock.release()
            if match is not None:
                draw(screen, lines, columns, 0, 20, 0, 29, match.get_string(), textwrap="n")
                draw(screen, lines, columns, 20, lines - 21, 0, 59, "\n".join(match.match_chat), alignv="b")
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
    ignore_next = False
    while True:
        c = msvcrt.getwch()
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
