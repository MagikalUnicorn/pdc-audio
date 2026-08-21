from __future__ import annotations

from pathlib import Path
import argparse
import struct
import uuid

ASF_HEADER_OBJECT = uuid.UUID('75b22630-668e-11cf-a6d9-00aa0062ce6c')
ASF_FILE_PROPERTIES_OBJECT = uuid.UUID('8cabdca1-a947-11cf-8ee4-00c00c205365')
ASF_EXTENDED_CONTENT_DESCRIPTION_OBJECT = uuid.UUID('d2d0a440-e307-11d2-97f0-00a0c95ea850')


def _u16(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from('<H', data, offset)[0]


def _u32(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from('<I', data, offset)[0]


def _u64(data: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from('<Q', data, offset)[0]


def _put_u16(data: bytearray, offset: int, value: int) -> None:
    struct.pack_into('<H', data, offset, value)


def _put_u64(data: bytearray, offset: int, value: int) -> None:
    struct.pack_into('<Q', data, offset, value)


def _guid(data: bytes | bytearray, offset: int) -> uuid.UUID:
    return uuid.UUID(bytes_le=bytes(data[offset:offset + 16]))


def iter_header_objects(data: bytes | bytearray):
    if len(data) < 30 or _guid(data, 0) != ASF_HEADER_OBJECT:
        raise ValueError('Not an ASF file or truncated ASF header')
    header_size = _u64(data, 16)
    object_count = _u32(data, 24)
    if header_size > len(data):
        raise ValueError('ASF header size exceeds file size')

    offset = 30
    for index in range(object_count):
        if offset + 24 > header_size:
            raise ValueError(f'Truncated ASF header object {index}')
        object_size = _u64(data, offset + 16)
        if object_size < 24 or offset + object_size > header_size:
            raise ValueError(f'Invalid ASF header object size at index {index}')
        yield index, offset, _guid(data, offset), object_size
        offset += object_size

    if offset != header_size:
        raise ValueError(f'ASF header objects end at {offset}, declared header ends at {header_size}')


def extract_descriptor_entry(source: bytes, descriptor_name: str) -> tuple[bytes, bytes]:
    wanted = descriptor_name.rstrip('\0')
    for _, offset, guid, object_size in iter_header_objects(source):
        if guid != ASF_EXTENDED_CONTENT_DESCRIPTION_OBJECT:
            continue
        count = _u16(source, offset + 24)
        cursor = offset + 26
        object_end = offset + object_size
        for _ in range(count):
            entry_start = cursor
            if cursor + 2 > object_end:
                raise ValueError('Truncated extended-content descriptor name length')
            name_length = _u16(source, cursor)
            cursor += 2
            if cursor + name_length + 4 > object_end:
                raise ValueError('Truncated extended-content descriptor')
            name_bytes = source[cursor:cursor + name_length]
            cursor += name_length
            value_type = _u16(source, cursor)
            value_length = _u16(source, cursor + 2)
            cursor += 4
            if cursor + value_length > object_end:
                raise ValueError('Truncated extended-content descriptor value')
            value = source[cursor:cursor + value_length]
            cursor += value_length
            name = name_bytes.decode('utf-16le').rstrip('\0')
            if name == wanted:
                if value_type != 1:
                    raise ValueError(f'{descriptor_name} is not an ASF BYTE_ARRAY descriptor')
                return bytes(source[entry_start:cursor]), bytes(value)
    raise ValueError(f'ASF descriptor {descriptor_name!r} was not found')


def add_descriptor(target: bytes, descriptor_entry: bytes, descriptor_name: str) -> bytes:
    data = bytearray(target)
    ecd_offset = None
    ecd_size = None
    file_properties_offset = None

    for _, offset, guid, object_size in iter_header_objects(data):
        if guid == ASF_EXTENDED_CONTENT_DESCRIPTION_OBJECT:
            ecd_offset = offset
            ecd_size = object_size
        elif guid == ASF_FILE_PROPERTIES_OBJECT:
            file_properties_offset = offset

    if ecd_offset is None or ecd_size is None:
        raise ValueError('Target ASF has no Extended Content Description Object')
    if file_properties_offset is None:
        raise ValueError('Target ASF has no File Properties Object')

    # Refuse duplicate names so that the preserved source value is unambiguous.
    count = _u16(data, ecd_offset + 24)
    cursor = ecd_offset + 26
    ecd_end = ecd_offset + ecd_size
    wanted = descriptor_name.rstrip('\0')
    for _ in range(count):
        name_length = _u16(data, cursor)
        cursor += 2
        name = bytes(data[cursor:cursor + name_length]).decode('utf-16le').rstrip('\0')
        cursor += name_length
        value_length = _u16(data, cursor + 2)
        cursor += 4 + value_length
        if name == wanted:
            raise ValueError(f'Target already contains descriptor {descriptor_name!r}')
    if cursor != ecd_end:
        raise ValueError('Malformed target Extended Content Description Object')

    old_header_size = _u64(data, 16)
    old_file_size = _u64(data, file_properties_offset + 40)
    delta = len(descriptor_entry)

    data[ecd_end:ecd_end] = descriptor_entry

    # The fields before the insertion keep the same offsets.
    _put_u16(data, ecd_offset + 24, count + 1)
    _put_u64(data, ecd_offset + 16, ecd_size + delta)
    _put_u64(data, 16, old_header_size + delta)
    _put_u64(data, file_properties_offset + 40, old_file_size + delta)

    if len(data) != len(target) + delta:
        raise AssertionError('Unexpected patched ASF size')
    return bytes(data)


def preserve_attachment(source_asf: Path, target_asf: Path, output_asf: Path) -> bytes:
    source = source_asf.read_bytes()
    target = target_asf.read_bytes()
    entry, payload = extract_descriptor_entry(source, 'SEMC PDC-AUDIO')
    output_asf.write_bytes(add_descriptor(target, entry, 'SEMC PDC-AUDIO'))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Copy the exact SEMC PDC-AUDIO extended-content descriptor into a remuxed ASF.'
    )
    parser.add_argument('source_asf', type=Path, help='Original Sony ASF containing SEMC PDC-AUDIO')
    parser.add_argument('target_asf', type=Path, help='Remuxed ASF containing decoded PCM audio')
    parser.add_argument('output_asf', type=Path, help='Output ASF containing both')
    args = parser.parse_args()
    payload = preserve_attachment(args.source_asf, args.target_asf, args.output_asf)
    print(f'Preserved SEMC PDC-AUDIO payload: {len(payload)} bytes')
    print(f'Wrote: {args.output_asf}')


if __name__ == '__main__':
    main()
