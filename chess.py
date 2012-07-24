# -*- coding: utf-8 -*-
#Copyright (c) 2012 Walter Bender

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# You should have received a copy of the GNU General Public License
# along with this library; if not, write to the Free Software
# Foundation, 51 Franklin Street, Suite 500 Boston, MA 02110-1335 USA


import gtk
import gobject
import cairo
import os
import subprocess
from string import find

from random import uniform

from gettext import gettext as _

import logging
_logger = logging.getLogger('gnuchess-activity')

from sprites import Sprites, Sprite

ROBOT_MOVE = 'My move is : '
TOP = 3
MID = 2
BOT = 1
ROBOT = 'robot'
RESTORE = 'restore'
REMOVE = 'remove'
UNDO = 'undo'
HINT = 'hint'
GAME = 'game'
NEW = 'new'
# Skin indicies
WP = 0
BP = 1
WR = 2
BR = 3
WN = 4
BN = 5
WB = 6
BB = 7
WQ = 8
BQ = 9
WK = 10
BK = 11
FILES = 'abcdefgh'
RANKS = '12345678'

class Gnuchess():

    def __init__(self, canvas, parent=None, path=None,
                 colors=['#A0FFA0', '#FF8080']):
        self._activity = parent
        self._bundle_path = path
        self._colors = ['#FFFFFF']
        self._colors.append(colors[0])
        self._colors.append(colors[1])
        self._colors.append('#000000')

        self._canvas = canvas
        if parent is not None:
            parent.show_all()
            self._parent = parent

        self._canvas.set_flags(gtk.CAN_FOCUS)
        self._canvas.add_events(gtk.gdk.BUTTON_PRESS_MASK)
        self._canvas.add_events(gtk.gdk.BUTTON_RELEASE_MASK)
        self._canvas.add_events(gtk.gdk.POINTER_MOTION_MASK)
        self._canvas.connect("expose-event", self._expose_cb)
        self._canvas.connect("button-press-event", self._button_press_cb)
        self._canvas.connect("button-release-event", self._button_release_cb)
        self._canvas.connect("motion-notify-event", self._mouse_move_cb)

        self._width = gtk.gdk.screen_width()
        self._height = gtk.gdk.screen_height()
        self._scale = int((self._height - 55) / 10)
        self.we_are_sharing = False
        self._saved_game = "foo"

        self.move_list = []
        self.game = ''
        self._showing_game_history = False

        self._press = None
        self._release = None
        self._dragpos = [0, 0]
        self._total_drag = [0, 0]
        self._last_piece_played = [None, (0, 0)]

        self._move = 0
        self._counter = 0

        self.white = []
        self.black = []
        self._board = []
        self._squares = []

        self.skins = []

        # Generate the sprites we'll need...
        self._sprites = Sprites(self._canvas)
        self._generate_sprites(colors)

        self._all_clear()

    def move(self, my_move):
        ''' Send a move to the saved gnuchess instance
        (1) set the color
        (2) force manual
        (3) reload any moves from the move list
        (4) and, if my_move is not None, add the new move
            or, if my_move == 'robot'
                then ask the computer to move by sending a go command
            or, refresh after a restore or a remove
        (5) show board to refresh the current state
        (6) prompt the robot to move
        '''
        _logger.debug(my_move)

        p = subprocess.Popen(['%s/bin/gnuchess' % (self._bundle_path)],
                             stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)

        if my_move == HINT:
            level = 'hard\nbook on\n'  # may as well get a good hint
        elif self._activity.playing_mode == 'easy':
            level = 'easy\nbook off\ndepth 1\n'
        else:
            level = 'hard\nbook on\n'

        if my_move in [REMOVE, UNDO, RESTORE, HINT, GAME, NEW]:
            hint = False
            if my_move == REMOVE:
                self.move_list = self.move_list[:-2]
            elif my_move == UNDO:
                self.move_list = self.move_list[:-1]
            cmd = 'force manual\n'
            for move in self.move_list:
                cmd += '%s\n' % (move)
            if my_move == HINT:
                # cmd += '%sshow moves\nquit\n' % (level)
                cmd += '%sgo\nquit\n' % (level)
                hint = True
            elif my_move == GAME:
                cmd += 'show game\nquit\n'
            else:
                cmd += 'show board\nquit\n'
            _logger.debug(cmd)
            output = p.communicate(input=cmd)
            self._process_output(output[0], my_move=None, hint=hint)
        elif my_move == ROBOT:  # Ask the computer to play
            cmd = 'force manual\n'
            for move in self.move_list:
                cmd += '%s\n' % (move)
            cmd += '%sgo\nshow board\nquit\n' % (level)
            _logger.debug(cmd)
            output = p.communicate(input=cmd)
            self._process_output(output[0], my_move='robot')
        elif my_move is not None:  # human's move
            cmd = 'force manual\n'
            for move in self.move_list:
                cmd += '%s\n' % (move)
            cmd += '%s\n' % (my_move)
            cmd += 'show board\nquit\n'
            _logger.debug(cmd)
            output = p.communicate(input=cmd)
            self._process_output(output[0], my_move=my_move)
        else:
            _logger.debug('my_move == None')

    def _process_output(self, output, my_move=None, hint=False):
        ''' process output '''
        check = False
        checkmate = False
        _logger.debug(output)
        if 'White   Black' in output:  # processing show game
            target = 'White   Black'
            output = output[find(output, target):]
            self.game = output[:find(output, '\n\n')]
            return
        elif hint:  # What would the robot do?
            output = output[find(output, ROBOT_MOVE):]
            hint = output[len(ROBOT_MOVE):find(output, '\n')]
            self._activity.status.set_label(hint)
            _logger.debug(hint)
            self._parse_move(hint)
            return
        elif 'wins' in output or 'loses' in output:
            checkmate = True
        elif 'Illegal move' in output:
            self._activity.status.set_label(_('Illegal move'))
            if self._last_piece_played[0] is not None:
                self._last_piece_played[0].move(self._last_piece_played[1])
                self._last_piece_played[0] = None
        elif my_move == ROBOT:
            output = output[find(output, ROBOT_MOVE):]
            robot_move = output[len(ROBOT_MOVE):find(output, '\n')]
            _logger.debug(robot_move)
            self.move_list.append(robot_move)
            if '+' in robot_move:
                check = True
            if '#' in robot_move or '++' in robot_move:
                checkmate = True
            if self._activity.playing_white:
                self._activity.black_entry.set_text(robot_move)
                self._activity.white_entry.set_text('')
            else:
                self._activity.white_entry.set_text(robot_move)
                self._activity.black_entry.set_text('')
        elif my_move is not None:
            self.move_list.append(my_move)
            if self._activity.playing_white:
                self._activity.white_entry.set_text(my_move)
                self._activity.black_entry.set_text('')
            else:
                self._activity.black_entry.set_text(my_move)
                self._activity.white_entry.set_text('')

        if len(self.move_list) % 2 == 0:
            target = 'white  '
        else:
            target = 'black  '
        _logger.debug('looking for %s' % (target))
        while find(output, target) > 0:
            output = output[find(output, target):]
            output = output[find(output, '\n'):]
        if len(output) < 136:
            self._activity.status.set_label(_('bad board output'))
            _logger.debug('bad board output')
            _logger.debug(output)
        else:
            self._load_board(output)

        if len(self.move_list) % 2 == 0:
            self._activity.status.set_label(_("It is White's move."))
        else:
            self._activity.status.set_label(_("It is Black's move."))

        if checkmate:
            self._activity.status.set_label(_('Checkmate'))
            _logger.debug('checkmate')
            return
        elif check:
            self._activity.status.set_label(_('Check'))
            _logger.debug('check')
            return
        elif my_move == ROBOT:
            _logger.debug('robot took a turn')
            return
        elif self._activity.playing_white and len(self.move_list) == 0:
            _logger.debug('new game (white)')
            return
        elif not self._activity.playing_white and len(self.move_list) == 1:
            _logger.debug('new game (black) robot played')
            return
        elif self._activity.playing_white and len(self.move_list) % 2 == 1:
            _logger.debug('asking computer to play black')
        elif not self._activity.playing_white and len(self.move_list) % 2 == 0:
            _logger.debug('asking computer to play white')

    def _all_clear(self):
        ''' Things to reinitialize when starting up a new game. '''
        self.bg.set_layer(-1)
        self.bg.set_label('')
        self.move_list = []
        self.game = ''
        self.move(NEW)

    def _initiating(self):
        return self._activity.initiating

    def new_game(self):
        self._all_clear()
        if not self._activity.playing_white:
            self.move(ROBOT)

    def restore_game(self, move_list):
        self.move_list = []
        
        for move in move_list:
            self.move_list.append(str(move))
        _logger.debug(self.move_list)
        if self._activity.playing_white:
            _logger.debug('really... restoring game to white')
        else:
            _logger.debug('really... restoring game to black')
        self.move(RESTORE)
        return

    def copy_game(self):
        self.move(GAME)
        _logger.debug(self.game)
        return self.game

    def save_game(self):
        return self.move_list

    def show_game_history(self):
        if not self._showing_game_history:
            self.bg.set_layer(TOP)
            self.bg.set_label(self.copy_game())
            self._showing_game_history = True
        else:
            self.bg.set_layer(-1)
            self.bg.set_label('')
            self._showing_game_history = False

    def play_game_history(self):
        self._counter = 0
        self._copy_of_move_list = self.move_list[:]
        self._all_clear()
        self._stepper()

    def _stepper(self):
        if self._counter < len(self._copy_of_move_list):
            self.move(self._copy_of_move_list[self._counter])
            self._counter += 1
            gobject.timeout_add(2000, self._stepper)

    def _button_press_cb(self, win, event):
        win.grab_focus()
        x, y = map(int, event.get_coords())

        self._dragpos = [x, y]
        self._total_drag = [0, 0]

        spr = self._sprites.find_sprite((x, y))
        if spr == None or spr.type == None:
            return
        
        if self._activity.playing_robot:
            if self._activity.playing_white and spr.type[0] in 'prnbqk':
                return
            elif not self._activity.playing_white and spr.type[0] in 'PRNBQK':
                return
        else:
            if len(self.move_list) % 2 == 0 and spr.type[0] in 'prnbqk':
                return
            elif len(self.move_list) % 2 == 1 and spr.type[0] in 'PRNBQK':
                return

        self._release = None
        self._press = spr
        self._press.set_layer(TOP)
        self._last_piece_played = [spr, spr.get_xy()]

        self._activity.status.set_label(spr.type)
        return True

    def _mouse_move_cb(self, win, event):
        """ Drag a tile with the mouse. """
        spr = self._press
        if spr is None:
            self._dragpos = [0, 0]
            return True
        win.grab_focus()
        x, y = map(int, event.get_coords())
        dx = x - self._dragpos[0]
        dy = y - self._dragpos[1]
        spr.move_relative([dx, dy])
        self._dragpos = [x, y]
        self._total_drag[0] += dx
        self._total_drag[1] += dy
        return True

    def _button_release_cb(self, win, event):
        win.grab_focus()

        self._dragpos = [0, 0]

        if self._press is None:
            return

        x, y = map(int, event.get_coords())
        spr = self._sprites.find_sprite((x, y))

        self._release = spr
        self._release.set_layer(MID)
        self._press = None
        self._release = None

        g1 = self._xy_to_file_and_rank(self._last_piece_played[1])
        g2 = self._xy_to_file_and_rank((x, y))
        if g1 == g2:  # We'll let beginners touch a piece and return it.
            spr.move(self._last_piece_played[1])
            return True

        move = '%s%s' % (g1, g2)

        # Queen a pawn (FIXME: really should be able to choose any piece)
        if spr.type == 'p' and g2[1] == '1':
            move += 'Q'
        elif spr.type == 'P' and g2[1] == '8':
            move += 'Q'

        if len(self.move_list) % 2 == 0:
            self._activity.white_entry.set_text(move)
        else:
            self._activity.black_entry.set_text(move)
        self.move(move)
        
        if self._activity.playing_robot:
            self._activity.status.set_label('Thinking')
            gobject.timeout_add(500, self.move, ROBOT)

        return True

    def undo(self):
        # TODO: Lock out while robot is playing
        if self._activity.playing_robot:
            if len(self.move_list) > 1:
                if len(self.move_list) % 2 == 0 and \
                   not self._activity.playing_white:
                    self.move(UNDO)
                else:
                    self.move(REMOVE)
        else:
            if len(self.move_list) > 0:
                self.move(UNDO)

    def hint(self):
        # TODO: Lock out while robot is playing
        self._activity.status.set_label('Thinking')
        gobject.timeout_add(500, self.move, HINT)

    def _flash_tile(self, sfile, srank, cfile, crank):
        tiles = []
        self._counter = 0
        tiles.append('%s%s' % (sfile, srank))
        tiles.append('%s%s' % (cfile, crank))
        _logger.debug(tiles)
        gobject.timeout_add(100, self._flasher, tiles)
        return

    def _flasher(self, tiles):
        if self._counter < 9:
            self._counter += 1
            for tile in tiles:
                i = self._file_and_rank_to_index(tile)
                if self._counter % 2 == 0:
                    self._board[i].set_image(self._squares[2])
                else:
                    self._board[i].set_image(self._squares[black_or_white(i)])
                self._board[i].set_layer(BOT)
            gobject.timeout_add(200, self._flasher, tiles)

    def _parse_move(self, move):
        label = move
        source_file = None
        source_rank = None
        capture_piece = None
        capture_file = None
        capture_rank = None
        if 'x' in move:
            capture = True
        else:
            capture = False
        if len(self.move_list) % 2 == 0:
            white = True
            if move[0] in FILES:
                piece = 'P'
                source_file = move[0]
                if move[1] in RANKS:
                    source_rank = move[1]
            elif move[0] == 'O':
                if move == 'O-O':
                    piece = 'K'
                    source_file = 'g'
                    source_rank = 1
                    print 'K and R[1] and g1 and f1'
                else:
                    print 'K and R[0] and c1 and d1'
            else:
                piece = move[0]
                if move[1] in FILES:
                    source_file = move[1]
                    if move[2] in RANKS:
                        source_rank = move[2]
                elif move[1] in RANKS:
                    source_rank = move[1]
        else:
            white = False
            if move[0] in FILES:
                piece = 'p'
                source_file = move[0]
                if move[1] in RANKS:
                    source_rank = move[1]
            elif move[0] == 'O':
                if move == 'O-O':
                    piece = 'k'
                    source_file = 'g'
                    source_rank = 8
                    print 'k and r[1] and g8 and f8'
                else:
                    print 'k and r[0] and c8 and d8'
            else:
                piece = move[0]
                if move[1] in FILES:
                    source_file = move[1]
                    if move[2] in RANKS:
                        source_rank = move[2]
                elif move[1] in RANKS:
                    source_rank = move[1]
        if capture:
            move = move[find(move, 'x') + 1:]
            if white:
                if move[0] in 'kqbnr':
                    capture_piece = move[0]
                    if len(move) > 1:
                        if move[1] in FILES:
                            capture_file = move[1]
                            if len(move) > 2:
                                if move[2] in RANKS:
                                    capture_rank = move[2]
                        elif move[1] in RANKS:
                            capture_rank = move[1]
                else:
                    capture_piece = 'p'
                    if move[0] in FILES:
                        capture_file = move[0]
                        if len(move) > 1:
                            if move[1] in RANKS:
                                capture_rank = move[1]
                    elif move[0] in RANKS:
                        capture_rank = move[0]
            else:
                if move[0] in 'KQBNR':
                    capture_piece = move[0]
                    if len(move) > 1:
                        if move[1] in FILES:
                            capture_file = move[1]
                            if len(move) > 2:
                                if move[2] in RANKS:
                                    capture_rank = move[2]
                        elif move[1] in RANKS:
                            capture_rank = move[1]
                else:
                    capture_piece = 'P'
                    if move[0] in FILES:
                        capture_file = move[0]
                        if len(move) > 1:
                            if move[1] in RANKS:
                                capture_rank = move[1]
                    elif move[0] in RANKS:
                        capture_rank = move[0]
        self._activity.status.set_label('%s: %s %s%s %s%s' % (
                label, piece, source_file, source_rank,
                capture_file, capture_rank))

        if capture_file is None:
            capture_file = source_file
        if capture_rank is None:
            capture_rank = source_rank
        if source_file is None:
            source_file = capture_file
        if source_rank is None:
            source_rank = capture_rank

        if piece in 'pP':
            source_file, source_rank = self._search_for_pawn(
                piece, source_file, source_rank, capture_file, capture_rank)
        elif piece in 'rR':
            source_file, source_rank = self._search_for_rook(
                piece, source_file, source_rank, capture_file, capture_rank)
        elif piece in 'nN':
            source_file, source_rank = self._search_for_knight(
                piece, source_file, source_rank, capture_file, capture_rank)
        elif piece in 'bB':
            source_file, source_rank = self._search_for_bishop(
                piece, source_file, source_rank, capture_file, capture_rank)
        elif piece in 'qQ':
            source_file, source_rank = self._search_for_queen(
                piece, source_file, source_rank, capture_file, capture_rank)
        elif piece in 'kK':
            source_file, source_rank = self._search_for_king(
                piece, source_file, source_rank, capture_file, capture_rank)
        self._flash_tile(source_file, source_rank, capture_file, capture_rank)

    def _search_for_pawn(
        self, piece, source_file, source_rank, capture_file, capture_rank):
        # Check for first move
        if piece == 'p' and capture_rank == '5':
            i = self._file_and_rank_to_index('%s7' % (capture_file))
            x, y = self._index_to_xy(i)
            for p in range(8):
                pos = self.black[8 + p].get_xy()
                if x == pos[0] and y == pos[1]:
                    return capture_file, '7'
        elif piece == 'P' and capture_rank == '4':
            i = self._file_and_rank_to_index('%s2' % (capture_file))
            x, y = self._index_to_xy(i)
            for p in range(8):
                pos = self.white[8 + p].get_xy()
                if x == pos[0] and y == pos[1]:
                    return capture_file, '7'
        # Check for previous space
        if piece == 'p':
            i = self._file_and_rank_to_index('%s%d' % (
                    capture_file, int(capture_rank) + 1))
            x, y = self._index_to_xy(i)
            for p in range(8):
                pos = self.black[8 + p].get_xy()
                if x == pos[0] and y == pos[1]:
                    return capture_file, str(int(capture_rank) + 1)
        elif piece == 'P':
            i = self._file_and_rank_to_index('%s%d' % (
                    capture_file, int(capture_rank) - 1))
            x, y = self._index_to_xy(i)
            for p in range(8):
                pos = self.black[8 + p].get_xy()
                if x == pos[0] and y == pos[1]:
                    return capture_file, str(int(capture_rank) - 1)
        # Check for capture
        if piece == 'p':
            if source_file == capture_file:
                f = FILES.index(capture_file)
                if f > 0:
                    i = self._file_and_rank_to_index('%s%d' % (
                            FILES[f - 1], int(capture_rank) + 1))
                    x, y = self._index_to_xy(i)
                    for p in range(8):
                        pos = self.black[8 + p].get_xy()
                        if x == pos[0] and y == pos[1]:
                            return FILES[f - 1], str(int(capture_rank) + 1)
                if f < 7:
                    i = self._file_and_rank_to_index('%s%d' % (
                            FILES[f + 1], int(capture_rank) + 1))
                    x, y = self._index_to_xy(i)
                    for p in range(8):
                        pos = self.black[8 + p].get_xy()
                        if x == pos[0] and y == pos[1]:
                            return FILES[f + 1], str(int(capture_rank) + 1)
            else:
                i = self._file_and_rank_to_index('%s%d' % (
                        source_file, int(capture_rank) + 1))
                x, y = self._index_to_xy(i)
                for p in range(8):
                    pos = self.black[8 + p].get_xy()
                    if x == pos[0] and y == pos[1]:
                        return source_file, str(int(capture_rank) + 1)
        if piece == 'P':
            if source_file == capture_file:
                f = FILES.index(capture_file)
                if f > 0:
                    i = self._file_and_rank_to_index('%s%d' % (
                            FILES[f - 1], int(capture_rank) - 1))
                    x, y = self._index_to_xy(i)
                    for p in range(8):
                        pos = self.white[8 + p].get_xy()
                        if x == pos[0] and y == pos[1]:
                            return FILES[f - 1], str(int(capture_rank) - 1)
                if f < 7:
                    i = self._file_and_rank_to_index('%s%d' % (
                            FILES[f + 1], int(capture_rank) - 1))
                    x, y = self._index_to_xy(i)
                    for p in range(8):
                        pos = self.white[8 + p].get_xy()
                        if x == pos[0] and y == pos[1]:
                            return FILES[f + 1], str(int(capture_rank) - 1)
            else:
                i = self._file_and_rank_to_index('%s%d' % (
                        source_file, int(capture_rank) - 1))
                x, y = self._index_to_xy(i)
                for p in range(8):
                    pos = self.white[8 + p].get_xy()
                    if x == pos[0] and y == pos[1]:
                        return source_file, str(int(capture_rank) - 1)
        return capture_file, capture_rank

    def _search_for_rook(
        self, piece, source_file, source_rank, capture_file, capture_rank):
        # Change rank
        if piece in 'rq':
            for r in range(8 - int(capture_rank)):
                i = self._file_and_rank_to_index('%s%d' % (
                        capture_file, int(capture_rank) + r))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if piece == 'r' and (b == 0 or b == 7):
                        return capture_file, str(int(capture_rank) + r)
                    elif piece == 'q' and b == 3:
                        return capture_file, str(int(capture_rank) + r)
                    else:
                        break
                elif p is not None:
                    break
            for r in range(int(capture_rank) - 1):
                i = self._file_and_rank_to_index('%s%d' % (
                        capture_file, int(capture_rank) - r))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if piece == 'r' and (b == 0 or b == 7):
                        return capture_file, str(int(capture_rank) - r)
                    elif piece == 'q' and b == 3:
                        return capture_file, str(int(capture_rank) - r)
                    else:
                        break
                elif p is not None:
                    break
        else:
            for r in range(8 - int(capture_rank)):
                i = self._file_and_rank_to_index('%s%d' % (
                        capture_file, int(capture_rank) + r))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if piece == 'R' and (w == 0 or w == 7):
                        return capture_file, str(int(capture_rank) + r)
                    elif piece == 'Q' and w == 3:
                        return capture_file, str(int(capture_rank) + r)
                    else:
                        break
                elif p is not None:
                    break
            for r in range(int(capture_rank) - 1):
                i = self._file_and_rank_to_index('%s%d' % (
                        capture_file, int(capture_rank) - r))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if piece == 'R' and (w == 0 or w == 7):
                        return capture_file, str(int(capture_rank) - r)
                    elif piece == 'Q' and w == 3:
                        return capture_file, str(int(capture_rank) - r)
                    else:
                        break
                elif p is not None:
                    break
        # Change file
        if piece in 'rq':
            for f in range(8 - FILES.index(capture_file)):
                i = self._file_and_rank_to_index('%s%s' % (
                        FILES[f + FILES.index(capture_file)], capture_rank))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if piece == 'r' and (b == 0 or b == 7):
                        return FILES[f + FILES.index(capture_file)], \
                               capture_rank
                    elif piece == 'q' and b == 3:
                        return FILES[f + FILES.index(capture_file)], \
                               capture_rank
                    if b == 0 or b == 7:
                        return FILES[f + FILES.index(capture_file)], \
                               capture_rank
                    else:
                        break
                elif p is not None:
                    break
            for f in range(FILES.index(capture_file) - 1):
                i = self._file_and_rank_to_index('%s%s' % (
                        FILES[FILES.index(capture_file) - f], capture_rank))
                p = self._find_piece_at_index(i)
                if p in self.black:
                    b = self.black.index(p)
                    if piece == 'r' and (b == 0 or b == 7):
                        return FILES[FILES.index(capture_file) - f], \
                               capture_rank
                    elif piece == 'q' and b == 3:
                        return FILES[FILES.index(capture_file) - f], \
                               capture_rank
                    else:
                        break
                elif p is not None:
                    break
        else:
            for f in range(8 - FILES.index(capture_file)):
                i = self._file_and_rank_to_index('%s%s' % (
                        FILES[f + FILES.index(capture_file)], capture_rank))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if piece == 'R' and (w == 0 or w == 7):
                        return FILES[f + FILES.index(capture_file)], \
                               capture_rank
                    elif piece == 'Q' and w == 3:
                        return FILES[f + FILES.index(capture_file)], \
                               capture_rank
                    else:
                        break
                elif p is not None:
                    break
            for f in range(FILES.index(capture_file) - 1):
                i = self._file_and_rank_to_index('%s%s' % (
                        FILES[FILES.index(capture_file) - f], capture_rank))
                p = self._find_piece_at_index(i)
                if p in self.white:
                    w = self.white.index(p)
                    if piece == 'R' and (w == 0 or w == 7):
                        return FILES[FILES.index(capture_file) - f], \
                               capture_rank
                    elif piece == 'Q' and w == 3:
                        return FILES[FILES.index(capture_file) - f], \
                               capture_rank
                    else:
                        break
                elif p is not None:
                    break
        if piece in 'rR':
            return capture_file, capture_rank
        else:
            return None, None

    def _search_for_knight(
        self, piece, source_file, source_rank, capture_file, capture_rank):
        return capture_file, capture_rank

    def _search_for_bishop(
        self, piece, source_file, source_rank, capture_file, capture_rank):
        return capture_file, capture_rank

    def _search_for_queen(
        self, piece, source_file, source_rank, capture_file, capture_rank):
        file_and_rank = self._search_for_rook(
            self, piece, source_file, source_rank, capture_file, capture_rank)
        if file_and_rank[0] is not None:
            return file_and_rank[0], file_and_rank[1]
        return self._search_for_bishop(
            self, piece, source_file, source_rank, capture_file, capture_rank)

    def _search_for_king(
        self, piece, source_file, source_rank, capture_file, capture_rank):
        return capture_file, capture_rank

    def _find_piece_at_index(self, i):
        pos = self._index_to_xy(i)
        return self._find_piece_at_xy(self, pos)

    def _find_piece_at_index(self, pos):
        for w in self.white:
            x, y = w.get_pos()
            if x == pos[0] and y == pos[1]:
                return w
        for b in self.black:
            x, y = b.get_pos()
            if x == pos[0] and y == pos[1]:
                return b
        return None

    def remote_button_press(self, dot, color):
        ''' Receive a button press from a sharer '''
        return

    def set_sharing(self, share=True):
        _logger.debug('enabling sharing')
        self.we_are_sharing = share

    def _file_and_rank_to_index(self, file_and_rank):
        ''' calculate the tile index from the file and rank '''
        return FILES.index(file_and_rank[0]) + \
            8 * (7 - RANKS.index(file_and_rank[1]))

    def _index_to_xy(self, i):
        return self._board[i].get_xy()

    def _xy_to_file_and_rank(self, pos):
        ''' calculate the board column and row for an xy position '''
        xo = self._width - 8 * self._scale
        xo = int(xo / 2)
        x = pos[0] - xo
        yo = int(self._scale / 2)
        y = yo
        return ('%s%d' % (FILES[int((pos[0] - xo) / self._scale)],
                8 - int((pos[1] - yo) / self._scale)))
 
    def _expose_cb(self, win, event):
        self.do_expose_event(event)

    def do_expose_event(self, event):
        ''' Handle the expose-event by drawing '''
        # Restrict Cairo to the exposed area
        cr = self._canvas.window.cairo_create()
        cr.rectangle(event.area.x, event.area.y,
                event.area.width, event.area.height)
        cr.clip()
        # Refresh sprite list
        self._sprites.redraw_sprites(cr=cr)

    def _destroy_cb(self, win, event):
        gtk.main_quit()

    def _load_board(self, board):
        ''' Load the board based on gnuchess board output '''
        white_pawns = 0
        white_rooks = 0
        white_knights = 0
        white_bishops = 0
        white_queens = 0
        black_pawns = 0
        black_rooks = 0
        black_knights = 0
        black_bishops = 0
        black_queens = 0
        w, h = self.white[0].get_dimensions()
        xo = self._width - 8 * self._scale
        xo = int(xo / 2)
        yo = int(self._scale / 2)
        for i in range(17):  # extra queen
            self.black[i].move((-self._scale, -self._scale))
            self.white[i].move((-self._scale, -self._scale))
        k = 1
        for i in range(8):
            x = xo
            y = yo + i * self._scale
            for j in range(8):
                piece = board[k]
                k += 2
                if piece in 'PRNBQK':  # white
                    if piece == 'P':
                        self.white[8 + white_pawns].move((x, y))
                        white_pawns += 1
                    elif piece == 'R':
                        if white_rooks == 0:
                            self.white[0].move((x, y))
                            white_rooks += 1
                        else:
                            self.white[7].move((x, y))
                            white_rooks += 1
                    elif piece == 'N':
                        if white_knights == 0:
                            self.white[1].move((x, y))
                            white_knights += 1
                        else:
                            self.white[6].move((x, y))
                            white_knights += 1
                    elif piece == 'B':
                        if white_bishops == 0:
                            self.white[2].move((x, y))
                            white_bishops += 1
                        else:
                            self.white[5].move((x, y))
                            white_bishops += 1
                    elif piece == 'Q':
                        if white_queens == 0:
                            self.white[3].move((x, y))
                            white_queens += 1
                        else:
                            self.white[16].move((x, y))
                            self.white[16].set_layer(MID)
                    elif piece == 'K':
                        self.white[4].move((x, y))
                elif piece in 'prnbqk':  # black
                    if piece == 'p':
                        self.black[8 + black_pawns].move((x, y))
                        black_pawns += 1
                    elif piece == 'r':
                        if black_rooks == 0:
                            self.black[0].move((x, y))
                            black_rooks += 1
                        else:
                            self.black[7].move((x, y))
                            black_rooks += 1
                    elif piece == 'n':
                        if black_knights == 0:
                            self.black[1].move((x, y))
                            black_knights += 1
                        else:
                            self.black[6].move((x, y))
                            black_knights += 1
                    elif piece == 'b':
                        if black_bishops == 0:
                            self.black[2].move((x, y))
                            black_bishops += 1
                        else:
                            self.black[5].move((x, y))
                            black_bishops += 1
                    elif piece == 'q':
                        if black_queens == 0:
                            self.black[3].move((x, y))
                            black_queens += 1
                        else:
                            self.black[16].move((x, y))
                            self.black[16].set_layer(MID)
                    elif piece == 'k':
                        self.black[4].move((x, y))
                x += self._scale
            x = xo
            y += self._scale
            k += 1

    def reskin(self, piece, file_path):
        DICT = {'white_pawn': WP, 'black_pawn': BP,
                'white_rook': WR, 'black_rook': BR,
                'white_knight': WN, 'black_knight': BN,
                'white_bishop': WB, 'black_bishop': BB,
                'white_queen': WQ, 'black_queen': BQ,
                'white_king': WK, 'black_king': BK}
        pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(
            file_path, self._scale, self._scale)
        self.skins[DICT[piece]] = pixbuf
        if piece == 'white_pawn':
            for i in range(8):
                self.white[i + 8].set_image(pixbuf)
        elif piece == 'black_pawn':
            for i in range(8):
                self.black[i + 8].set_image(pixbuf)
        elif piece == 'white_rook':
            self.white[0].set_image(pixbuf)
            self.white[7].set_image(pixbuf)
        elif piece == 'black_rook':
            self.black[0].set_image(pixbuf)
            self.black[7].set_image(pixbuf)
        elif piece == 'white_knight':
            self.white[1].set_image(pixbuf)
            self.white[6].set_image(pixbuf)
        elif piece == 'black_knight':
            self.black[1].set_image(pixbuf)
            self.black[6].set_image(pixbuf)
        elif piece == 'white_bishop':
            self.white[2].set_image(pixbuf)
            self.white[5].set_image(pixbuf)
        elif piece == 'black_bishop':
            self.black[2].set_image(pixbuf)
            self.black[5].set_image(pixbuf)
        elif piece == 'white_queen':
            self.white[3].set_image(pixbuf)
            self.white[16].set_image(pixbuf)
        elif piece == 'black_queen':
            self.black[3].set_image(pixbuf)
            self.black[16].set_image(pixbuf)
        elif piece == 'white_king':
            self.white[4].set_image(pixbuf)
        elif piece == 'black_king':
            self.black[4].set_image(pixbuf)

    def _generate_sprites(self, colors):
        self.bg = Sprite(self._sprites, 0, 0, self._box(
                self._width, self._height, color=colors[1]))
        self.bg.set_layer(-1)
        self.bg.set_margins(l=10, t=10, r=10, b=10)
        self.bg.set_label_attributes(12, horiz_align="left", vert_align="top")
        self.bg.type = None

        w = h = self._scale
        self._squares.append(self._box(w, h, color='black'))
        self._squares.append(self._box(w, h, color='white'))
        self._squares.append(self._box(w, h, color=colors[0]))
        xo = self._width - 8 * self._scale
        xo = int(xo / 2)
        yo = int(self._scale / 2)
        y = yo
        for i in range(8):
            x = xo
            for j in range(8):
                self._board.append(
                    Sprite(self._sprites, x, y,
                           self._squares[black_or_white([i, j])]))
                self._board[-1].type = None  # '%s%d' % (FILES[j], 8 - i)
                self._board[-1].set_layer(BOT)
                x += self._scale
            y += self._scale

        self.skins.append(gtk.gdk.pixbuf_new_from_file_at_size(
                '%s/icons/white-pawn.svg' % (self._bundle_path), w, h))
        self.skins.append(gtk.gdk.pixbuf_new_from_file_at_size(
                '%s/icons/black-pawn.svg' % (self._bundle_path), w, h))
        self.skins.append(gtk.gdk.pixbuf_new_from_file_at_size(
                '%s/icons/white-rook.svg' % (self._bundle_path), w, h))
        self.skins.append(gtk.gdk.pixbuf_new_from_file_at_size(
                '%s/icons/black-rook.svg' % (self._bundle_path), w, h))
        self.skins.append(gtk.gdk.pixbuf_new_from_file_at_size(
                '%s/icons/white-knight.svg' % (self._bundle_path), w, h))
        self.skins.append(gtk.gdk.pixbuf_new_from_file_at_size(
                '%s/icons/black-knight.svg' % (self._bundle_path), w, h))
        self.skins.append(gtk.gdk.pixbuf_new_from_file_at_size(
                '%s/icons/white-bishop.svg' % (self._bundle_path), w, h))
        self.skins.append(gtk.gdk.pixbuf_new_from_file_at_size(
                '%s/icons/black-bishop.svg' % (self._bundle_path), w, h))
        self.skins.append(gtk.gdk.pixbuf_new_from_file_at_size(
                '%s/icons/white-queen.svg' % (self._bundle_path), w, h))
        self.skins.append(gtk.gdk.pixbuf_new_from_file_at_size(
                '%s/icons/black-queen.svg' % (self._bundle_path), w, h))
        self.skins.append(gtk.gdk.pixbuf_new_from_file_at_size(
                '%s/icons/white-king.svg' % (self._bundle_path), w, h))
        self.skins.append(gtk.gdk.pixbuf_new_from_file_at_size(
                '%s/icons/black-king.svg' % (self._bundle_path), w, h))

        self.white.append(Sprite(self._sprites, 0, 0, self.skins[WR]))
        self.white[-1].type = 'R'
        self.white[-1].set_layer(MID)
        self.white.append(Sprite(self._sprites, 0, 0, self.skins[WN]))
        self.white[-1].type = 'N'
        self.white[-1].set_layer(MID)
        self.white.append(Sprite(self._sprites, 0, 0, self.skins[WB]))
        self.white[-1].type = 'B'
        self.white[-1].set_layer(MID)
        self.white.append(Sprite(self._sprites, 0, 0, self.skins[WQ]))
        self.white[-1].type = 'Q'
        self.white[-1].set_layer(MID)
        self.white.append(Sprite(self._sprites, 0, 0, self.skins[WK]))
        self.white[-1].type = 'K'
        self.white[-1].set_layer(MID)
        self.white.append(Sprite(self._sprites, 0, 0, self.skins[WB]))
        self.white[-1].type = 'B'
        self.white[-1].set_layer(MID)
        self.white.append(Sprite(self._sprites, 0, 0, self.skins[WN]))
        self.white[-1].type = 'N'
        self.white[-1].set_layer(MID)
        self.white.append(Sprite(self._sprites, 0, 0, self.skins[WR]))
        self.white[-1].type = 'R'
        self.white[-1].set_layer(MID)
        for i in range(8):
            self.white.append(Sprite(self._sprites, 0, 0, self.skins[WP]))
            self.white[-1].type = 'P'
            self.white[-1].set_layer(MID)
        self.white.append(Sprite(self._sprites, 0, 0, self.skins[WQ]))
        self.white[-1].type = 'Q'
        self.white[-1].hide()  # extra queen for pawn

        self.black.append(Sprite(self._sprites, 0, 0, self.skins[BR]))
        self.black[-1].type = 'r'
        self.black[-1].set_layer(MID)
        self.black.append(Sprite(self._sprites, 0, 0, self.skins[BN]))
        self.black[-1].type = 'n'
        self.black[-1].set_layer(MID)
        self.black.append(Sprite(self._sprites, 0, 0, self.skins[BB]))
        self.black[-1].type = 'b'
        self.black[-1].set_layer(MID)
        self.black.append(Sprite(self._sprites, 0, 0, self.skins[BQ]))
        self.black[-1].type = 'q'
        self.black[-1].set_layer(MID)
        self.black.append(Sprite(self._sprites, 0, 0, self.skins[BK]))
        self.black[-1].type = 'k'
        self.black[-1].set_layer(MID)
        self.black.append(Sprite(self._sprites, 0, 0, self.skins[BB]))
        self.black[-1].type = 'b'
        self.black[-1].set_layer(MID)
        self.black.append(Sprite(self._sprites, 0, 0, self.skins[BN]))
        self.black[-1].type = 'n'
        self.black[-1].set_layer(MID)
        self.black.append(Sprite(self._sprites, 0, 0, self.skins[BR]))
        self.black[-1].type = 'r'
        self.black[-1].set_layer(MID)
        for i in range(8):
            self.black.append(Sprite(self._sprites, 0, 0, self.skins[BP]))
            self.black[-1].type = 'p'
            self.black[-1].set_layer(MID)
        self.black.append(Sprite(self._sprites, 0, 0, self.skins[BQ]))
        self.black[-1].type = 'q'
        self.black[-1].hide()  # extra queen for pawn

    def _box(self, w, h, color='black'):
        ''' Generate a box '''
        self._svg_width = w
        self._svg_height = h
        return svg_str_to_pixbuf(
                self._header() + \
                self._rect(self._svg_width, self._svg_height, 0, 0,
                           color=color) + \
                self._footer())

    def _header(self):
        return '<svg\n' + 'xmlns:svg="http://www.w3.org/2000/svg"\n' + \
            'xmlns="http://www.w3.org/2000/svg"\n' + \
            'xmlns:xlink="http://www.w3.org/1999/xlink"\n' + \
            'version="1.1"\n' + 'width="' + str(self._svg_width) + '"\n' + \
            'height="' + str(self._svg_height) + '">\n'

    def _rect(self, w, h, x, y, color='black'):
        svg_string = '       <rect\n'
        svg_string += '          width="%f"\n' % (w)
        svg_string += '          height="%f"\n' % (h)
        svg_string += '          rx="%f"\n' % (0)
        svg_string += '          ry="%f"\n' % (0)
        svg_string += '          x="%f"\n' % (x)
        svg_string += '          y="%f"\n' % (y)
        if color == 'black':
            svg_string += 'style="fill:#000000;stroke:#000000;"/>\n'
        elif color == 'white':
            svg_string += 'style="fill:#ffffff;stroke:#ffffff;"/>\n'
        else:
            svg_string += 'style="fill:%s;stroke:%s;"/>\n' % (color, color)
        return svg_string

    def _footer(self):
        return '</svg>\n'


def svg_str_to_pixbuf(svg_string):
    """ Load pixbuf from SVG string """
    pl = gtk.gdk.PixbufLoader('svg')
    pl.write(svg_string)
    pl.close()
    pixbuf = pl.get_pixbuf()
    return pixbuf


def black_or_white(n):
    ''' Return 0 is it is a black square; 1 if it is a white square '''
    if type(n) is int:
        i = int(n / 8)
        j = n % 8
    else:
        i = n[0]
        j = n[1]

    if i % 2 == 0:
        if (i * 8 + j) % 2 == 1:
            return 0
        else:
            return 1
    else:
        if (i * 8 + j) % 2 == 1:
            return 1
        else:
            return 0



