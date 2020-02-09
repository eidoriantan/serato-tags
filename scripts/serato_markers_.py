#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import os
import ast
import configparser
import io
import math
import shutil
import struct
import subprocess
import sys
import tempfile
import enum
import mutagen

FMT_VERSION = 'BB'


class EntryType(enum.IntEnum):
    INVALID = 0
    CUE = 1
    LOOP = 3


def color_from_rgb(rgb):
    r, g, b = struct.unpack('BBB', rgb)
    z = b & 0x7F
    y = ((b >> 7) | (g << 1)) & 0x7F
    x = ((g >> 6) | (r << 2)) & 0x7F
    w = (r >> 5)
    return bytes(bytearray([w, x, y, z]))


def color_to_rgb(data):
    w, x, y, z = struct.unpack('BBBB', data)
    b = (z & 0x7F) | ((y & 0x01) << 7)
    g = ((y & 0x7F) >> 1) | ((x & 0x03) << 6)
    r = ((x & 0x7F) >> 2) | ((w & 0x07) << 5)
    return struct.pack('BBB', r, g, b)


class Entry(object):
    FMT = '>BI1sI6s4sBB'
    FIELDS = ('is_set', 'start_position', 'field3', 'end_position', 'field5',
              'color', 'type', 'field6')

    def __init__(self, *args):
        assert len(args) == len(self.FIELDS)
        for field, value in zip(self.FIELDS, args):
            setattr(self, field, value)

    def __repr__(self):
        return '{name}({data})'.format(
            name=self.__class__.__name__,
            data=', '.join('{}={!r}'.format(name, getattr(self, name))
                           for name in self.FIELDS))

    @classmethod
    def load(cls, data):
        info_size = struct.calcsize(cls.FMT)
        info = struct.unpack(cls.FMT, data[:info_size])
        entry_data = []
        for field, value in zip(cls.FIELDS, info):
            if field == 'is_set':
                assert value in (0x00, 0x7F)
                value = True if not value else False
            elif field in ('color', 'color_mask'):
                value = color_to_rgb(value)
            elif field == 'start_position' and value == 0x7F7F7F7F:
                value = None
            elif field == 'end_position' and value == 0x7F7F7F7F:
                value = None
            elif field == 'type':
                value = EntryType(value)
            entry_data.append(value)

        return cls(*entry_data)

    def dump(self):
        entry_data = []
        for field in self.FIELDS:
            value = getattr(self, field)
            if field == 'is_set':
                value = 0x7F if not value else 0x00
            elif field in ('color', 'color_mask'):
                value = color_from_rgb(value)
            elif field == 'start_position' and value is None:
                value = 0x7F7F7F7F
            elif field == 'end_position' and value is None:
                value = 0x7F7F7F7F
            elif field == 'type':
                value = int(value)
            entry_data.append(value)
        return struct.pack(self.FMT, *entry_data)


class Color(Entry):
    FMT = '>4s'
    FIELDS = ('color_mask',)


def parse(fp):
    assert struct.unpack(FMT_VERSION, fp.read(2)) == (0x02, 0x05)

    num_entries = struct.unpack('>I', fp.read(4))[0]
    for i in range(num_entries):
        entry_data = fp.read(0x16)
        assert len(entry_data) == 0x16

        entry = Entry.load(entry_data)
        yield entry

    yield Color.load(fp.read())


def dump(new_entries):
    data = struct.pack(FMT_VERSION, 0x02, 0x05)
    num_entries = len(new_entries) - 1
    data += struct.pack('>I', num_entries)
    for entry_data in new_entries:
        data += entry_data.dump()
    return data


def ui_ask(question, choices, default=None):
    text = '{question} [{choices}]? '.format(
        question=question,
        choices='/'.join(
            x.upper() if x == default else x
            for x in (*choices.keys(), '?')
        )
    )

    while True:
        answer = input(text).lower()
        if default and answer == '':
            answer = default

        if answer in choices.keys():
            return answer
        else:
            print('\n'.join(
                '{} - {}'.format(choice, desc)
                for choice, desc in (*choices.items(), ('?', 'print help'))
            ))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('file', metavar='FILE')
    parser.add_argument('-e', '--edit', action='store_true')
    args = parser.parse_args(argv)

    if args.edit:
        text_editor = shutil.which(os.getenv('EDITOR', 'vi'))
        if not text_editor:
            print('No suitable $EDITOR found.', file=sys.stderr)
            return 1

        hex_editor = shutil.which(os.getenv('HEXEDITOR', 'bvi'))
        if not hex_editor:
            print('No suitable HEXEDITOR found.', file=sys.stderr)
            return 1

    tagfile = mutagen.File(args.file)
    if tagfile is not None:
        try:
            data = tagfile['GEOB:Serato Markers_'].data
        except KeyError:
            print('File is missing "GEOB:Serato Markers_" tag')
            return 1
    else:
        with open(args.file, mode='rb') as fp:
            data = fp.read()

    entries = list(parse(io.BytesIO(data)))
    new_entries = []
    action = None

    width = math.floor(math.log10(len(entries)))+1
    for entry_index, entry in enumerate(entries):
        if args.edit:
            if action not in ('q', '_'):
                print('{:{}d}: {!r}'.format(entry_index, width, entry))
                action = ui_ask('Edit this entry', {
                    'y': 'edit this entry',
                    'n': 'do not edit this entry',
                    'q': ('quit; do not edit this entry or any of the '
                          'remaining ones'),
                    'a': 'edit this entry and all later entries in the file',
                    'b': 'edit raw bytes',
                    'r': 'remove this entry',
                }, default='n')

            if action in ('y', 'a', 'b'):
                while True:
                    with tempfile.NamedTemporaryFile() as f:
                        if action == 'b':
                            f.write(entry.dump())
                            editor = hex_editor
                        else:
                            if action == 'a':
                                entries_to_edit = ((
                                    '{:{}d}: {}'.format(
                                        i, width,
                                        repr(e.type) if e.__class__ == Entry
                                        else 'Color'),
                                    e,
                                ) for i, e in enumerate(
                                    entries[entry_index:], start=entry_index))
                            else:
                                entries_to_edit = (
                                    (repr(entry.type)
                                     if entry.__class__ == Entry else 'Color',
                                     entry),)

                            for section, e in entries_to_edit:
                                f.write('[{}]\n'.format(section).encode())
                                for field in e.FIELDS:
                                    value = getattr(e, field)
                                    if field == 'type':
                                        value = int(value)
                                    f.write('{}: {!r}\n'.format(
                                        field, value,
                                    ).encode())
                                f.write(b'\n')
                            editor = text_editor
                        f.flush()
                        status = subprocess.call((editor, f.name))
                        f.seek(0)
                        output = f.read()

                    if status != 0:
                        if ui_ask('Command failed, retry', {
                            'y': 'edit again',
                            'n': 'leave unchanged',
                        }) == 'n':
                            break
                    else:
                        try:
                            if action != 'b':
                                cp = configparser.ConfigParser()
                                cp.read_string(output.decode())
                                sections = tuple(sorted(cp.sections()))
                                if action != 'a':
                                    assert len(sections) == 1

                                results = []
                                for section in sections:
                                    l, s, r = section.partition(': ')
                                    name = r if s else l
                                    cls = Color if name == 'Color' else Entry
                                    e = cls(*(
                                        ast.literal_eval(
                                            cp.get(section, field),
                                        ) for field in cls.FIELDS
                                    ))
                                    results.append(cls.load(e.dump()))
                            else:
                                results = [entry.load(output)]
                        except Exception as e:
                            print(str(e))
                            if ui_ask('Content seems to be invalid, retry', {
                                'y': 'edit again',
                                'n': 'leave unchanged',
                            }) == 'n':
                                break
                        else:
                            for i, e in enumerate(results, start=entry_index):
                                print('{:{}d}: {!r}'.format(i, width, e))
                            subaction = ui_ask(
                                'Above content is valid, save changes', {
                                    'y': 'save current changes',
                                    'n': 'discard changes',
                                    'e': 'edit again',
                                }, default='y')
                            if subaction == 'y':
                                new_entries.extend(results)
                                if action == 'a':
                                    action = '_'
                                break
                            elif subaction == 'n':
                                if action == 'a':
                                    action = 'q'
                                new_entries.append(entry)
                                break
            elif action in ('r', '_'):
                continue
            else:
                new_entries.append(entry)
        else:
            print('{:{}d}: {!r}'.format(entry_index, width, entry))

    if args.edit:
        if new_entries == entries:
            print('No changes made.')
        else:
            new_data = dump(new_entries)

            if tagfile is not None:
                tagfile['GEOB:Serato Markers_'] = mutagen.id3.GEOB(
                    encoding=0,
                    mime='application/octet-stream',
                    desc='Serato Markers_',
                    data=new_data,
                )
                tagfile.save()
            else:
                with open(args.file, mode='wb') as fp:
                    fp.write(new_data)

    return 0


if __name__ == '__main__':
    sys.exit(main())
