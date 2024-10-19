#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import struct
import io
import sys

def swap_16le(b):
    blen = len(b)
    if blen % 2 > 0:
        raise Exception("Bytes were not UTF-16 encoded")

    swapped = bytearray()
    for i in range(0, blen - 1, 2):
        swapped.append(b[i + 1])
        swapped.append(b[i])

    return bytes(swapped)

FIELDPARSERS = {
    'b': lambda x: struct.unpack('?', x)[0],
    'o': lambda x: tuple(parse(io.BytesIO(x))),
    'p': lambda x: swap_16le(x).decode('utf-16'),
    'r': lambda x: tuple(parse(io.BytesIO(x))),
    's': lambda x: struct.unpack('>H', x)[0],
    't': lambda x: swap_16le(x).decode('utf-16'),
    'u': lambda x: struct.unpack('>I', x)[0],
}

FIELDWRITERS = {
    'b': lambda x: struct.pack('?', x),
    'o': lambda x: dump(x),
    'p': lambda x: b'\00' + x.encode('utf-16')[2:-1],
    'r': lambda x: dump(x),
    's': lambda x: struct.pack('>H', x),
    't': lambda x: b'\00' + x.encode('utf-16')[2:-1],
    'u': lambda x: struct.pack('>I', x)
}

FIELDNAMES = {
    # Database
    'vrsn': 'Version',
    'otrk': 'Track',
    'ttyp': 'File Type',
    'pfil': 'File Path',
    'tsng': 'Song Title',
    'tlen': 'Length',
    'tbit': 'Bitrate',
    'tsmp': 'Sample Rate',
    'tbpm': 'BPM',
    'tadd': 'Date added',
    'uadd': 'Date added',
    'tkey': 'Key',
    'bbgl': 'Beatgrid Locked',
    'tart': 'Artist',
    'utme': 'File Time',
    'bmis': 'Missing',
    # Crates
    'osrt': 'Sorting',
    'brev': 'Reverse Order',
    'ovct': 'Column Title',
    'tvcn': 'Column Name',
    'tvcw': 'Column Width',
    'ptrk': 'Track Path',
}


def parse(fp):
    for i, header in enumerate(iter(lambda: fp.read(8), b'')):
        assert len(header) == 8
        name_ascii, length = struct.unpack('>4sI', header)

        name = name_ascii.decode('ascii')
        type_id = name[0]

        # vrsn field has no type_id, but contains text
        if name == 'vrsn':
            type_id = 't'

        data = fp.read(length)
        assert len(data) == length

        try:
            fieldparser = FIELDPARSERS[type_id]
            value = fieldparser(data)
        except KeyError:
            value = data
        except UnicodeDecodeError:
            print(f"Unable to parse data: ({name}, {data})")
            value = data

        yield name, length, value

def dump(entries):
    data = b''
    for name, _, value in entries:
        type_id = name[0] if name != 'vrsn' else 't'
        try:
            fieldwriter = FIELDWRITERS[type_id]
        except KeyError:
            encoded = value
        else:
            encoded = fieldwriter(value)

        header = struct.pack('>4sI', name.encode('ascii'), len(encoded))
        assert len(header) == 8
        data += header + encoded
    return data

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('file', metavar='FILE', type=argparse.FileType('rb'))
    args = parser.parse_args(argv)

    for name, length, value in parse(args.file):
        fieldname = FIELDNAMES.get(name, 'Unknown')
        if isinstance(value, tuple):
            print('{name} ({fieldname}, {length} B)'.format(
                name=name,
                fieldname=fieldname,
                length=length,
            ))
            for name, length, value in value:
                fieldname = FIELDNAMES.get(name, 'Unknown')
                print('  {name} ({fieldname}, {length} B): {value!r}'.format(
                    name=name,
                    fieldname=fieldname,
                    length=length,
                    value=value,
                ))
        else:
            print('{name} ({length} B): {value!r}'.format(
                name=name,
                length=length,
                fieldname=fieldname,
                value=value,
            ))

    return 0


if __name__ == '__main__':
    sys.exit(main())
