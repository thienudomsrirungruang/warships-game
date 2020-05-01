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

need_redraw = threading.Event()
need_redraw.set()

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
                need_redraw.set()
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
            draw(screen, lines, columns, lines - 1, 1, 0, columns, current_line, alignh="l", textwrap="n")
            current_line_lock.release()
            chat_lock.acquire()
            draw(screen, lines, columns, 0, lines - 1, 60, columns - 60, "\n".join(chat_list), alignv="b")
            chat_lock.release()
            sys.stdout.write("\n" + "\n".join(["".join(_) for _ in screen]))
            time.sleep(.03)
            # current_line_lock.acquire()
            # print("hi")
            # sys.stdout.write("{}\n".format(current_line))
            # current_line_lock.release()

# alignh : "l" for left, "m" for middle, "r" for right
# alignv : "t" for top, "m" for middle, "b" for bottom
# textwrap: "n" for none, "w" for words, "g" for greedy
def draw(screen, lines, columns, startl, numl, startc, numc, content, alignh="l", alignv="t", padding=" ", textwrap="w"):
    subscreen = [[padding] * numc for _ in range(numl)]
    # print(len(subscreen), len(subscreen[0]))
    text_lines = content.splitlines()
    if textwrap == "g":
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
        # print(current_line)
        current_line_lock.release()

def main(server_ip, server_port):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((server_ip, server_port))
        start_new_thread(send, (sock,))
        start_new_thread(receive, (sock,))
        start_new_thread(listen_for_keypress, ())
        start_new_thread(redraw, ())
        start_new_thread(start_client, ())
    except ConnectionError as e:
        print("ERROR: {}".format(e))
        exit()
    while True:
        time.sleep(.1)

if __name__ == '__main__':
    main(SERVER_IP, SERVER_PORT)
    # redraw()
    # while True:
    #     time.sleep(.1)
