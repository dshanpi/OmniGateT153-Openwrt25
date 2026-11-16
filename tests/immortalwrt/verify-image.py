#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Independently verify an ImmortalWrt v25.12.2 T153 disk against its build inputs.

Inputs are read-only. Private temporary files are used for extraction and ext4
normalization; neither the source tree nor the supplied image is modified.
A retained raw image is published only after every software check passes.
This program never accesses a board or claims hardware validation.
"""
import argparse
import bz2
from datetime import datetime, timezone
import gzip
import hashlib
import json
import lzma
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import tempfile
import zlib

BOARD = 'dshanpi_t153mx-omnigate'
KERNEL = '6.12.103'
DIST = 'ImmortalWrt'
RELEASE = '25.12.2'
REVISION = 'r38135-0c4cd0f9920a'
SOURCE_EPOCH = 1788681816
KERNEL_ARCHIVE_SHA256 = 'f143aaade8877ba5616e788b4482576db28481bcf557ef537f4fcc3938fc3176'

MIB = 1024 * 1024
SPL_OFFSET, PROPER_OFFSET = 8192, 131072
BOOT_OFFSET, BOOT_BYTES, ROOT_OFFSET = 4 * MIB, 32 * MIB, 36 * MIB


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(MIB), b''):
            h.update(block)
    return h.hexdigest()


def info(path):
    path = Path(path)
    need(path.is_file(), 'missing regular input: ' + str(path))
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest(path)}


def one(paths, label):
    paths = list(paths)
    need(len(paths) == 1, 'expected one ' + label + ', found ' + str(len(paths)))
    return paths[0]


def run(argv, env=None):
    p = subprocess.run([str(x) for x in argv], stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True, env=env)
    return {'command': [str(x) for x in argv], 'returncode': p.returncode,
            'output': p.stdout}


def checked(argv, env=None):
    result = run(argv, env)
    need(result['returncode'] == 0, 'command failed: ' + ' '.join(result['command']) + '\n' + result['output'])
    return result


def host_tool(source, name):
    path = source / 'staging_dir/host/bin' / name
    need(path.is_file() and os.access(path, os.X_OK), 'missing staged host tool: ' + str(path))
    return path


def cross_tool(source, name):
    return one(source.glob('staging_dir/toolchain-*/bin/*-linux-muslgnueabi-' + name), 'cross ' + name)


def text(value):
    need(value.endswith(b'\0'), 'unterminated DT string')
    return value.rstrip(b'\0').decode()


def fdt_nodes(data):
    need(len(data) >= 40, 'short FDT header')
    magic, total, off, strings, _rsv, version, _last, _cpu, strings_len, struct_len = struct.unpack_from('>10I', data)
    need(magic == 0xd00dfeed and 40 <= total <= len(data) and version >= 17, 'FDT header')
    end_struct, end_strings = off + struct_len, strings + strings_len
    need(40 <= off < end_struct <= total and 40 <= strings < end_strings <= total, 'FDT block bounds')
    nodes, stack = {}, []
    while off + 4 <= end_struct:
        token = struct.unpack_from('>I', data, off)[0]
        off += 4
        if token == 1:
            end = data.index(0, off, end_struct)
            stack.append(data[off:end].decode())
            path = '/' + '/'.join(stack[1:])
            need(path not in nodes, 'duplicate FDT node')
            nodes[path] = {}
            off = (end + 4) & ~3
        elif token == 2:
            need(stack, 'unmatched FDT END_NODE')
            stack.pop()
        elif token == 3:
            need(stack and off + 8 <= end_struct, 'FDT property header')
            size, nameoff = struct.unpack_from('>II', data, off)
            off += 8
            need(off + size <= end_struct and nameoff < strings_len, 'FDT property bounds')
            end = data.index(0, strings + nameoff, end_strings)
            name = data[strings + nameoff:end].decode()
            props = nodes['/' + '/'.join(stack[1:])]
            need(name not in props, 'duplicate FDT property')
            props[name] = data[off:off + size]
            off = (off + size + 3) & ~3
        elif token == 4:
            continue
        elif token == 9:
            need(not stack, 'unclosed FDT nodes')
            return nodes
        else:
            raise ValueError('unknown FDT token ' + str(token))
    raise ValueError('missing FDT END')


def legacy(data, kind, load=None):
    need(len(data) >= 64, 'short legacy image')
    magic, hcrc, stamp, size, address, entry, crc = struct.unpack_from('>7I', data)
    need(magic == 0x27051956 and len(data) == size + 64, 'legacy magic or length')
    header = bytearray(data[:64])
    header[4:8] = bytes(4)
    need(zlib.crc32(header) == hcrc and zlib.crc32(data[64:]) == crc, 'legacy header/data CRC')
    need(data[29:32] == bytes([2, kind, 0]), 'legacy ARM/type/compression')
    if load is not None:
        need(address == entry == load and data[28] == 17, 'U-Boot load/entry/OS')
    return data[64:], stamp


def bootarea(area):
    need(area[4:12] == b'eGON.BT0', 'SPL eGON header')
    branch, checksum, size = struct.unpack_from('<I8xII', area)
    need(branch == 0xea000016 and 96 <= size <= 0x18000 and size % 8192 == 0, 'SPL branch/size')
    check = bytearray(area[:size])
    struct.pack_into('<I', check, 12, 0x5f0a6c39)
    need(sum(struct.unpack('<%dI' % (size // 4), check)) & 0xffffffff == checksum, 'SPL checksum')
    relative = PROPER_OFFSET - SPL_OFFSET
    need(size < relative and area[size:relative] == bytes(relative - size), 'SPL/UBoot gap')
    proper, _ = legacy(area[relative:], 5, 0x4a000000)
    need(b'Four-core PSCI cold-boot profile' in proper, 'four-core U-Boot marker')
    need(SPL_OFFSET + len(area) < BOOT_OFFSET, 'bootloader/partition overlap')
    return {'spl_bytes': size, 'proper_bytes': len(area) - relative,
            'bytes': len(area), 'sha256': sha(area), 'spl_offset': SPL_OFFSET,
            'proper_offset': PROPER_OFFSET}


def copy_region(image, output, offset, size):
    with image.open('rb') as src, output.open('wb') as dst:
        src.seek(offset)
        while size:
            block = src.read(min(MIB, size))
            need(block, 'truncated partition')
            dst.write(block)
            size -= len(block)


def fit_kernel(fit, kdir):
    nodes = fdt_nodes(fit)
    cfg = nodes['/configurations/' + text(nodes['/configurations']['default'])]
    need('ramdisk' not in cfg, 'persistent FIT selects a ramdisk')
    paths = ['/images/' + text(cfg[key]) for key in ('kernel', 'fdt')]
    kernel, dt = (nodes[path] for path in paths)
    for path, props in nodes.items():
        need(not (path.startswith('/images/') and props.get('type') == b'ramdisk\0'), 'FIT ramdisk image')
    for path in paths:
        algorithms = set()
        payload = nodes[path]['data']
        for child, props in nodes.items():
            if child.startswith(path + '/hash') and '/' not in child[len(path) + 1:]:
                algo = text(props['algo'])
                need(algo in ('crc32', 'sha1', 'sha256'), 'unsupported FIT hash')
                actual = struct.pack('>I', zlib.crc32(payload)) if algo == 'crc32' else hashlib.new(algo, payload).digest()
                need(actual == props['value'], 'FIT hash mismatch: ' + child)
                algorithms.add(algo)
        need({'crc32', 'sha1'} <= algorithms, 'missing FIT CRC32/SHA1')
    need(all(text(kernel[k]) == v for k, v in {'arch':'arm','os':'linux','type':'kernel','compression':'gzip'}.items()), 'FIT kernel properties')
    need(kernel['load'] == kernel['entry'] == struct.pack('>I', 0x48008000), 'FIT load/entry')
    need(text(dt['type']) == 'flat_dt' and text(dt['compression']) == 'none', 'FIT DT format')
    zimage = gzip.decompress(kernel['data'])
    need(zimage == (kdir/'zImage').read_bytes(), 'FIT differs from ordinary build zImage')
    need(struct.unpack_from('<I', zimage, 0x24)[0] == 0x016f2818, 'ARM zImage magic')
    dtb = kdir/('linux-' + KERNEL)/'arch/arm/boot/dts/allwinner/sun8i-t153-dshanpi-omnigate.dtb'
    need(dt['data'] == dtb.read_bytes(), 'FIT DTB differs from this build')
    board = fdt_nodes(dt['data'])
    need(b'dshanpi,t153mx-omnigate' in board['/']['compatible'].split(b'\0'), 'wrong board DTB')
    need(board['/chosen']['stdout-path'] == b'serial0:115200n8\0', 'DT console')
    cpus = {path: props for path,props in board.items() if path.startswith('/cpus/') and props.get('device_type') == b'cpu\0'}
    need(len(cpus) == 4, 'DT must describe four CPUs')
    need(sorted(struct.unpack('>I', p['reg'])[0] for p in cpus.values()) == [0,1,2,3], 'DT CPU IDs')
    need(all(p.get('enable-method') == b'psci\0' and p.get('status', b'okay\0') != b'disabled\0' for p in cpus.values()), 'DT CPU enable method')
    need(board['/psci']['method'] == b'smc\0', 'DT PSCI method')
    return zimage, {'bytes':len(fit),'sha256':sha(fit),'zimage_bytes':len(zimage),
        'zimage_sha256':sha(zimage),'dtb_sha256':sha(dt['data']),'load':'0x48008000',
        'entry':'0x48008000','cpu_ids':[0,1,2,3],
        'dtb_note':'Raw DT is fixed up by source U-Boot; no runtime memory/PSCI claim.'}


def decoded_kernel(zimage):
    candidates = []
    # The shipped ARM configuration uses XZ. Also handle other stdlib codecs
    # without mistaking a magic sequence in decompressor code for the payload.
    for codec, magic in [('xz',b'\xfd7zXZ\0'), ('gzip',b'\x1f\x8b\x08'), ('bzip2',b'BZh'), ('lzma',b'\x5d\x00')]:
        offset = -1
        while True:
            offset = zimage.find(magic, offset + 1)
            if offset < 0: break
            try:
                if codec in ('xz','lzma'):
                    dec = lzma.LZMADecompressor(format=lzma.FORMAT_XZ if codec == 'xz' else lzma.FORMAT_ALONE)
                    raw = dec.decompress(zimage[offset:], max_length=64*MIB+1)
                elif codec == 'gzip':
                    dec = zlib.decompressobj(31)
                    raw = dec.decompress(zimage[offset:], 64*MIB+1)
                else:
                    dec = bz2.BZ2Decompressor()
                    raw = dec.decompress(zimage[offset:], max_length=64*MIB+1)
                if dec.eof and len(raw) <= 64*MIB and re.search(rb'Linux version ' + re.escape(KERNEL.encode()) + rb' ', raw):
                    candidates.append((codec,offset,raw))
            except (lzma.LZMAError,zlib.error,OSError,EOFError,ValueError):
                pass
    need(len(candidates) == 1, 'cannot uniquely decode the expected ImmortalWrt kernel from ordinary zImage')
    return candidates[0]


def minimal_cpio(data):
    off, entries = 0, {}
    while off + 110 <= len(data):
        need(data[off:off+6] in (b'070701',b'070702'), 'embedded cpio header')
        fields = [int(data[off+6+i*8:off+14+i*8],16) for i in range(13)]
        mode,size,namesize = fields[1],fields[6],fields[11]
        off += 110
        need(namesize > 0 and off + namesize <= len(data) and data[off+namesize-1] == 0, 'cpio name bounds')
        name = data[off:off+namesize-1].decode()
        need('\0' not in name, 'cpio embedded NUL')
        off = (off + namesize + 3) & ~3
        need(off + size <= len(data), 'cpio data bounds')
        if name == 'TRAILER!!!':
            need(size == 0 and not any(data[off:]), 'cpio trailing payload or concatenated archive')
            need(set(entries) == {'dev','dev/console','root'}, 'unexpected minimal cpio entries')
            return entries
        need(name not in entries and name in ('dev','dev/console','root') and size == 0, 'populated initramfs or duplicate entry: ' + name)
        need(stat.S_IFMT(mode) == (stat.S_IFCHR if name == 'dev/console' else stat.S_IFDIR), 'unexpected cpio object type')
        if name == 'dev/console':
            need(fields[9:11] == [5,1], 'minimal cpio console device number')
        entries[name] = {'mode': oct(mode), 'bytes': size}
        off = (off + size + 3) & ~3
    raise ValueError('missing cpio trailer')


def persistent_kernel(zimage, kdir, source, work):
    codec, offset, raw = decoded_kernel(zimage)
    elf = kdir/'vmlinux.debug'
    need(elf.read_bytes()[:7] == b'\x7fELF\x01\x01\x01', 'ordinary kernel ELF32 little endian')
    nm = checked([cross_tool(source,'nm'),elf])['output']
    symbols = {}
    for line in nm.splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[2] in ('_text','__initramfs_start','__initramfs_size'):
            symbols[fields[2]] = int(fields[0],16)
    need(all(name in symbols for name in ('_text','__initramfs_start','__initramfs_size')),
         'ordinary debug ELF must retain all initramfs verification symbols')
    binary = work/'ordinary-elf.bin'
    checked([cross_tool(source,'objcopy'),'-O','binary','-R','.comment','-S',elf,binary])
    need(binary.read_bytes() == raw, 'decompressed zImage does not match ordinary vmlinux.debug')
    result = {'version':KERNEL,'codec':codec,'payload_offset':offset,'decoded_bytes':len(raw),
        'decoded_sha256':sha(raw),'ordinary_elf':info(elf),'elf_payload_identical':True,
        'populated_initramfs':False,'has_init':False}
    if '__initramfs_start' in symbols or '__initramfs_size' in symbols:
        need('__initramfs_start' in symbols and '__initramfs_size' in symbols, 'incomplete initramfs symbols')
        begin = symbols['__initramfs_start'] - symbols['_text']
        size_at = symbols['__initramfs_size'] - symbols['_text']
        need(0 <= begin < size_at <= len(raw)-4, 'initramfs symbol bounds')
        size = struct.unpack_from('<I',raw,size_at)[0]
        need(0 < size <= 4096 and begin + size <= size_at, 'populated or malformed built-in initramfs')
        result.update({'builtin_cpio_bytes':size,'builtin_cpio_entries':minimal_cpio(raw[begin:begin+size])})
    else:
        result['builtin_cpio_bytes'] = 0
    release = (kdir/('linux-'+KERNEL)/'include/config/kernel.release').read_text().strip()
    need(release == KERNEL, 'build kernel.release differs from expected ImmortalWrt kernel')
    config = (kdir/('linux-'+KERNEL)/'.config').read_text()
    for name in ('EXT4_FS','MMC','MMC_BLOCK','MMC_SUNXI','SERIAL_8250_CONSOLE','SMP','ARM_PSCI_FW'):
        need('CONFIG_'+name+'=y\n' in config, 'kernel needs built-in '+name)
    return result


def ext4_metadata_changes(original, final):
    """Allow only bitmap tail bits and fsck bookkeeping/checksum fields.

File data, inode tables, directory blocks, allocation bits for real inodes,
geometry, and group counters must remain byte-for-byte unchanged.
"""
    with original.open('rb') as f:
        f.seek(1024); sb = f.read(1024)
    need(sb[56:58] == b'\x53\xef', 'ext4 magic')
    inodes, blocks = struct.unpack_from('<II',sb)
    first, log_size = struct.unpack_from('<II',sb,20)
    blocksize = 1024 << log_size
    bpg, ipg = struct.unpack_from('<I',sb,32)[0], struct.unpack_from('<I',sb,40)[0]
    compat,incompat,ro = struct.unpack_from('<III',sb,92)
    need(not incompat & 0x10, 'metadata delta audit does not support meta_bg')
    if incompat & 0x80: blocks |= struct.unpack_from('<I',sb,336)[0] << 32
    groups = (blocks - first + bpg - 1)//bpg
    descsize = max(32,struct.unpack_from('<H',sb,254)[0]) if incompat & 0x80 else 32
    need(blocks * blocksize == original.stat().st_size == final.stat().st_size, 'ext4 geometry/partition size')
    table_start = (first + 1) * blocksize
    with original.open('rb') as f:
        f.seek(table_start); descriptors=f.read(groups*descsize)
    with final.open('rb') as f:
        f.seek(table_start); final_descriptors=f.read(groups*descsize)
    unused_corrections=[]
    ranges=[]
    def add(start,length,label): ranges.append((start,start+length,label))
    def sparse_group(group):
        if group in (0,1): return True
        for base in (3,5,7):
            value=group
            while value > 1 and value % base == 0: value//=base
            if value == 1: return True
        return False
    backup_groups=struct.unpack_from('<II',sb,588) if compat & 0x200 else ()
    bitmaps=[]
    for group in range(groups):
        desc=descriptors[group*descsize:(group+1)*descsize]
        bitmap=struct.unpack_from('<I',desc,4)[0]
        if descsize>=64: bitmap |= struct.unpack_from('<I',desc,36)[0]<<32
        valid=min(ipg,max(0,inodes-group*ipg))
        bitmaps.append((bitmap*blocksize,valid))
        final_desc=final_descriptors[group*descsize:(group+1)*descsize]
        old_unused=struct.unpack_from('<H',desc,28)[0]
        new_unused=struct.unpack_from('<H',final_desc,28)[0]
        if descsize>=64:
            old_unused |= struct.unpack_from('<H',desc,50)[0]<<16
            new_unused |= struct.unpack_from('<H',final_desc,50)[0]<<16
        if struct.unpack_from('<H',final_desc,18)[0] & 1:
            expected_unused=valid  # BG_INODE_UNINIT means all inodes unused.
        else:
            with final.open('rb') as f:
                f.seek(bitmap*blocksize); bits=f.read((valid+7)//8)
            last_used=next((i for i in range(valid-1,-1,-1) if bits[i//8] & (1<<(i%8))),-1)
            expected_unused=valid-last_used-1
        need(new_unused==expected_unused,'inode-table unused count disagrees with allocation bitmap')
        if old_unused!=new_unused:
            unused_corrections.append({'group':group,'before':old_unused,'after':new_unused,
                                       'independently_computed':expected_unused})
        has_super=(group==0 or (group in backup_groups if compat & 0x200 else (not ro & 1 or sparse_group(group))))
        if has_super:
            start=1024 if group==0 else (first+group*bpg)*blocksize
            for pos,length,label in [(48,4,'superblock_write_time'),(58,2,'superblock_state'),(64,4,'superblock_lastcheck'),(1020,4,'superblock_checksum')]:
                add(start+pos,length,label)
            tables=table_start if group==0 else (first+group*bpg+1)*blocksize
            for i in range(groups):
                add(tables+i*descsize+28,2,'inode_table_unused_count')
                if descsize>=64: add(tables+i*descsize+50,2,'inode_table_unused_count_hi')
                add(tables+i*descsize+26,2,'inode_bitmap_checksum')
                add(tables+i*descsize+30,2,'group_descriptor_checksum')
                if descsize>=64: add(tables+i*descsize+58,2,'inode_bitmap_checksum_hi')
    counts={}
    changed=0
    with original.open('rb') as a, final.open('rb') as b:
        offset=0
        while True:
            old,new=a.read(MIB),b.read(MIB)
            need(len(old)==len(new), 'rootfs delta length')
            if not old: break
            if old!=new:
                for i,(before,after) in enumerate(zip(old,new)):
                    if before==after: continue
                    pos=offset+i
                    label=None
                    for start,valid in bitmaps:
                        if start<=pos<start+blocksize and (pos-start)*8+7>=valid:
                            first_invalid=max(0,valid-(pos-start)*8)
                            mask=(0xff<<first_invalid)&0xff
                            if after == (before|mask): label='inode_bitmap_unused_padding'
                            break
                    if label is None:
                        label=next((name for start,end,name in ranges if start<=pos<end),None)
                    need(label is not None, 'unexpected ext4 content change at byte '+str(pos))
                    counts[label]=counts.get(label,0)+1
                    changed+=1
            offset+=len(old)
    return {'changed_bytes':changed,'changes_by_region':counts,'file_data_and_inode_tables_unchanged':True,
        'block_size':blocksize,'block_groups':groups,'inodes':inodes,
        'inode_table_unused_corrections':unused_corrections}


def release_fields(content):
    """Read simple generated release assignments without executing shell text."""
    fields = {}
    for line in content.splitlines():
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        if not re.fullmatch(r'[A-Z][A-Z0-9_]*', key):
            continue
        need(key not in fields, 'duplicate release field: ' + key)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        fields[key] = value
    return fields


def source_identity(source):
    """Expect independently pinned stable-tag values, never infer from the image."""
    need((source/'version').read_text().strip() == REVISION, 'source revision is not ImmortalWrt v25.12.2')
    need((source/'version.date').read_text().strip() == str(SOURCE_EPOCH), 'source version.date differs from stable archive')
    kernel = (source/'target/linux/generic/kernel-6.12').read_text()
    need('LINUX_VERSION-6.12 = .103' in kernel.splitlines(), 'source kernel version differs from stable archive')
    need('LINUX_KERNEL_HASH-' + KERNEL + ' = ' + KERNEL_ARCHIVE_SHA256 in kernel.splitlines(), 'source kernel archive hash differs from stable archive')
    version_mk = (source/'include/version.mk').read_text()
    for key, value in [('VERSION_NUMBER', RELEASE), ('VERSION_CODE', REVISION), ('VERSION_DIST', DIST)]:
        need(key + ':=$(if $(' + key + '),$(' + key + '),' + value + ')' in version_mk.splitlines(),
             'source release default differs: ' + key)
    return {'distribution': DIST, 'release': RELEASE, 'revision': REVISION,
            'kernel': KERNEL, 'source_date_epoch': SOURCE_EPOCH,
            'kernel_archive_sha256': KERNEL_ARCHIVE_SHA256}


def package_database(content, kind):
    packages = {}
    for stanza in content.split('\n\n'):
        fields = {}
        for line in stanza.splitlines():
            if ':' in line:
                key, value = line.split(':', 1)
                fields[key] = value.strip()
        name, version = (fields.get('P'), fields.get('V')) if kind == 'apk' else (fields.get('Package'), fields.get('Version'))
        if not name:
            continue
        if kind == 'opkg':
            state = fields.get('Status', '').split()
            if len(state) != 3 or state[0] != 'install' or state[2] != 'installed':
                continue
        need(version and name not in packages, 'invalid or duplicate installed package: ' + name)
        packages[name] = version
    need(packages, 'empty or unsupported installed package database')
    return packages


def https_backend(config, manifested, installed):
    """Reject libustream file collisions, including APK ABI-suffixed names.

    libmbedtls itself remains allowed for wpad-basic-mbedtls; it is the
    competing libustream backend and legacy HTTPS metapackage/tool that conflict.
    """
    values = dict(re.findall(r'^CONFIG_PACKAGE_([A-Za-z0-9+_.-]+)=(y|m)$', config, re.M))
    selected = sorted(name for name in values if name.startswith('libustream-'))
    need(selected == ['libustream-openssl'] and values['libustream-openssl'] == 'y',
         'HTTPS requires only built-in libustream-openssl; selected: ' + ', '.join(selected))
    for name in ('luci-ssl', 'px5g-mbedtls'):
        need(name not in values, 'legacy HTTPS package is selected: ' + name)
        need(name not in manifested and name not in installed, 'legacy HTTPS package is installed: ' + name)
    for name in ('luci-ssl-openssl', 'px5g-openssl', 'libopenssl'):
        need(values.get(name) == 'y', 'OpenSSL HTTPS package must be built-in: ' + name)
    backend_name = 'libustream-openssl20201210'
    for label, database in [('manifest', manifested), ('image package database', installed)]:
        backends = {name for name in database if name.startswith('libustream-')}
        need(backends == {backend_name}, 'HTTPS libustream backend conflict or absence in ' + label + ': ' + ', '.join(sorted(backends)))
        for name in ('luci-ssl-openssl', 'px5g-openssl', 'libopenssl3'):
            need(name in database, 'OpenSSL HTTPS package missing from ' + label + ': ' + name)
    for name in (backend_name, 'luci-ssl-openssl', 'px5g-openssl', 'libopenssl3'):
        need(manifested[name] == installed[name], 'HTTPS package version differs between image and manifest: ' + name)
    return {'exclusive_backend': backend_name, 'backend_version': installed[backend_name],
            'openssl_library': 'libopenssl3', 'openssl_version': installed['libopenssl3'],
            'luci_meta_package': 'luci-ssl-openssl', 'certificate_tool': 'px5g-openssl',
            'config_manifest_and_image_database_agree': True,
            'libmbedtls_allowed_for_wpad': True}


def installed_packages(rootfs, rootdir, source, config, out, requirement_path):
    requirement_path = requirement_path.resolve()
    requirements = json.loads(requirement_path.read_text())
    names = requirements.get('packages')
    excluded = requirements.get('excluded_packages', [])
    need(isinstance(excluded, list) and all(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9+_.-]*', name) for name in excluded), 'invalid excluded package list')
    need(isinstance(names, list) and names, 'required packages must be a nonempty JSON packages list')
    need(all(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9+_.-]*', name) for name in names), 'invalid required package name')
    need(len(set(names)) == len(names), 'duplicate required package')
    need(not set(names) & set(excluded), 'package cannot be both required and excluded')
    for name in names:
        need('CONFIG_PACKAGE_' + name + '=y\n' in config, 'required package not selected as built-in: ' + name)
    manifest = one(out.glob('*' + BOARD + '.manifest'), 'device package manifest')
    manifested = {}
    for line in manifest.read_text().splitlines():
        if not line.strip():
            continue
        name, separator, version = line.partition(' - ')
        need(separator and version and name not in manifested, 'malformed or duplicate package manifest entry')
        manifested[name] = version
    candidates = [(rootdir/'lib/apk/db/installed', 'apk'),
                  (rootdir/'usr/lib/opkg/status', 'opkg')]
    database, kind = one((candidate for candidate in candidates if candidate[0].is_file()), 'installed package database')
    need(not database.is_symlink(), 'package database must be a regular file')
    image_path = '/' + database.relative_to(rootdir).as_posix()
    result = subprocess.run([str(host_tool(source, 'debugfs')), '-R', 'cat ' + image_path, str(rootfs)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    need(result.returncode == 0 and result.stdout == database.read_bytes(), 'image package database differs from root-sunxi')
    installed = package_database(result.stdout.decode('utf-8'), kind)
    https = https_backend(config, manifested, installed)
    found = {}
    for name in names:
        need(name in manifested, 'required package missing from final manifest: ' + name)
        need(name in installed, 'required package missing from image package database: ' + name)
        need(manifested[name] == installed[name], 'package version differs between image and manifest: ' + name)
        found[name] = installed[name]
    for name in excluded:
        need('CONFIG_PACKAGE_' + name + '=y\n' not in config, 'excluded package is selected: ' + name)
        need(name not in manifested and name not in installed, 'excluded package is installed: ' + name)
    return {'requirements': info(requirement_path), 'manifest': info(manifest),
            'database_path': image_path, 'database_sha256': sha(result.stdout),
            'required_count': len(names), 'required_packages': found,
            'excluded_packages_absent': excluded,
            'https_backend': https,
            'config_manifest_and_image_database_agree': True}


def image_regular_bytes(rootfs, rootdir, source, name):
    """Read the actual disk partition, then bind those bytes to root-sunxi."""
    need(name.startswith('/') and '..' not in Path(name).parts, 'invalid image file path')
    original = rootdir/name.lstrip('/')
    need(original.is_file() and not original.is_symlink(), 'expected installed regular file: ' + str(original))
    result = subprocess.run([str(host_tool(source, 'debugfs')), '-R', 'cat ' + name, str(rootfs)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    need(result.returncode == 0 and result.stdout == original.read_bytes(),
         'actual image file differs from root-sunxi: ' + name)
    return result.stdout


def aic_vermagic(readelf_output):
    values = re.findall(r'\bvermagic=([^\r\n]+)', readelf_output)
    need(len(values) == 1, 'AIC module must have exactly one vermagic entry')
    value = values[0].strip()
    fields = value.split()
    need(fields and fields[0] == KERNEL, 'AIC module vermagic kernel mismatch: ' + value)
    need('SMP' in fields[1:], 'AIC module vermagic lacks SMP: ' + value)
    return value


def aic_image_content(rootfs, rootdir, source, config):
    """Check final AIC ELF module ABI and all pinned device firmware bytes."""
    for package in ('kmod-aic8800-t153-sdio', 'aic8800d80-firmware'):
        need('CONFIG_PACKAGE_' + package + '=y\n' in config, 'AIC image check needs ' + package)
    expected_path = source/'package/kernel/aic8800-t153-sdio/files/firmware-sha256.json'
    expected_bytes = expected_path.read_bytes()
    expected = json.loads(expected_bytes)
    source_commit = expected.get('source_commit')
    need(source_commit == 'd9c72efd382ccdbf2f1fdb09d2d4f3cc212edd9d', 'unexpected AIC firmware source commit')
    makefile = (expected_path.parent.parent/'Makefile').read_text()
    need('PKG_SOURCE_VERSION:=' + source_commit in makefile.splitlines(), 'AIC package source and firmware manifest disagree')
    entries = expected.get('files')
    need(isinstance(entries, dict) and entries, 'firmware hash manifest must have nonempty files')
    for name, value in entries.items():
        need(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_.-]+', name) and name not in ('.', '..'),
             'invalid firmware basename')
        need(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value), 'invalid firmware SHA256: ' + name)
    manifest_name = '/usr/share/aic8800d80/firmware-sha256.json'
    need(image_regular_bytes(rootfs, rootdir, source, manifest_name) == expected_bytes,
         'installed firmware manifest differs from package source')
    firmware_dir = rootdir/'lib/firmware/aic8800D80'
    need(firmware_dir.is_dir() and not firmware_dir.is_symlink(), 'missing regular AIC firmware directory')
    need({item.name for item in firmware_dir.iterdir()} == set(entries),
         'installed AIC firmware file inventory differs from pinned manifest')
    firmware = {}
    for name, expected_sha in sorted(entries.items()):
        image_name = '/lib/firmware/aic8800D80/' + name
        payload = image_regular_bytes(rootfs, rootdir, source, image_name)
        actual_sha = sha(payload)
        need(actual_sha == expected_sha, 'actual image firmware SHA256 mismatch: ' + name)
        firmware[image_name] = {'bytes': len(payload), 'sha256': actual_sha}
    modules = {}
    readelf = cross_tool(source, 'readelf')
    for name in ('aic8800_bsp', 'aic8800_fdrv'):
        relative = Path('lib/modules')/KERNEL/(name + '.ko')
        module = rootdir/relative
        candidates = sorted((rootdir/'lib/modules').rglob(name + '.ko*'))
        need(candidates == [module], 'AIC module missing, duplicated, stale or unexpectedly compressed: ' + name)
        image_name = '/' + relative.as_posix()
        payload = image_regular_bytes(rootfs, rootdir, source, image_name)
        need(len(payload) >= 52 and payload[:7] == b'\x7fELF\x01\x01\x01', 'AIC module is not ELF32 little endian: ' + name)
        need(struct.unpack_from('<HH', payload, 16) == (1, 40), 'AIC module is not an ARM relocatable ELF: ' + name)
        modinfo = checked([readelf, '-p', '.modinfo', module])['output']
        value = aic_vermagic(modinfo)
        modules[image_name] = {'bytes': len(payload), 'sha256': sha(payload),
                               'vermagic': value, 'architecture': 'ARM ELF32 little endian'}
    return {'scope': 'Final disk bytes checked; no module loading, radio initialization or hardware verification.',
            'expected_kernel': KERNEL, 'smp_required': True,
            'firmware_source_manifest': info(expected_path),
            'firmware_source_commit': source_commit, 'firmware_files': firmware,
            'modules': modules, 'image_and_root_sunxi_identical': True}


def installed_files(rootfs, rootdir, source, config):
    debugfs=host_tool(source,'debugfs')
    paths=['/etc/openwrt_release','/usr/lib/os-release','/sbin/init','/sbin/procd',
           '/etc/board.d/02_network','/lib/upgrade/platform.sh','/etc/config/firewall',
           '/etc/uci-defaults/99-t153-immortal']
    if 'CONFIG_PACKAGE_aic8800d80-bt=y\n' in config:
        paths += ['/usr/sbin/aic8800d80-bt','/etc/init.d/aic8800d80-bt','/etc/config/aic8800d80-bt']
    result={}
    for name in paths:
        original=rootdir/name.lstrip('/')
        need(original.is_file() and not original.is_symlink(), 'expected installed regular file: '+str(original))
        p=subprocess.run([str(debugfs),'-R','cat '+name,str(rootfs)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        need(p.returncode==0 and p.stdout==original.read_bytes(), 'installed file differs from root-sunxi: '+name)
        result[name]={'bytes':len(p.stdout),'sha256':sha(p.stdout)}
    link=rootdir/'etc/os-release'
    need(link.is_symlink() and os.readlink(link)=='../usr/lib/os-release', 'source os-release symlink')
    link_info=checked([debugfs,'-R','stat /etc/os-release',rootfs])['output']
    need('Fast link dest: "../usr/lib/os-release"' in link_info, 'image os-release symlink')
    release=(rootdir/'etc/openwrt_release').read_text()
    release_values = release_fields(release)
    for key, value in [('DISTRIB_ID', DIST), ('DISTRIB_RELEASE', RELEASE),
                       ('DISTRIB_REVISION', REVISION), ('DISTRIB_TARGET', 'sunxi/cortexa7')]:
        need(release_values.get(key) == value, 'incorrect installed release ' + key)
    osrelease = release_fields((rootdir/'usr/lib/os-release').read_text())
    for key, value in [('NAME', DIST), ('ID', DIST.lower()),
                       ('VERSION_ID', RELEASE), ('BUILD_ID', REVISION),
                       ('OPENWRT_BOARD', 'sunxi/cortexa7')]:
        need(osrelease.get(key) == value, 'incorrect os-release ' + key)
    return result


def verify(args, report, work):
    source=args.source.resolve()
    report['expected_identity'] = source_identity(source)
    config=(source/'.config').read_text()
    root_mib=int(one(re.findall(r'^CONFIG_TARGET_ROOTFS_PARTSIZE=(\d+)$',config,re.M),'rootfs size config'))
    need('CONFIG_TARGET_sunxi_cortexa7_DEVICE_'+BOARD+'=y\n' in config, 'T153 single-device profile not selected')
    need('CONFIG_TARGET_ROOTFS_EXT4FS=y\n' in config, 'ext4 not selected')
    epoch=int((source/'version.date').read_text().strip())
    epoch=max(epoch,315532800)
    env=dict(os.environ,TZ='UTC',LC_ALL='C',E2FSCK_TIME=str(epoch),E2FSPROGS_FAKE_TIME=str(epoch))
    kdir=one((p.parent for p in source.glob('build_dir/target-*/linux-sunxi_cortexa7/linux-'+KERNEL) if p.is_dir()),'native kernel build')
    stage=one(source.glob('staging_dir/target-*/image/'+BOARD+'-u-boot-with-spl.bin'),'staged bootarea').parent
    original_root=args.rootfs_source.resolve() if args.rootfs_source else kdir/'root.ext4'
    rootdir=kdir.parent/'root-sunxi'
    out=source/'bin/targets/sunxi/cortexa7'
    image=args.image.resolve() if args.image else one(out.glob('*'+BOARD+'-ext4-raw.img.gz'),'native compressed disk')
    report.update({'source':str(source),'image':info(image),'config':info(source/'.config'),
        'source_date_epoch':epoch,'rootfs_mib':root_mib,'hardware_verified':False,
        'scope':'Software-only final ImmortalWrt image validation; no board access or hardware claims.'})
    expected=(root_mib+36)*MIB
    raw=work/'disk.img'
    total=0
    with gzip.open(image,'rb') as src,raw.open('wb') as dst:
        for block in iter(lambda:src.read(MIB),b''):
            total+=len(block)
            need(total<=expected,'decompressed disk larger than partition geometry')
            dst.write(block)
    need(total==expected,'decompressed disk size')
    report['raw_image']=info(raw)
    with raw.open('rb') as f:
        mbr=f.read(512)
        expected_mbr=bytearray(512)
        struct.pack_into('<I',expected_mbr,440,0x15302512)
        for i,start,sectors,kind in [(0,8192,65536,0x0e),(1,73728,root_mib*2048,0x83)]:
            struct.pack_into('<B3sB3sII',expected_mbr,446+i*16,0x80 if i==0 else 0,b'\xfe\xff\xff',kind,b'\xfe\xff\xff',start,sectors)
        expected_mbr[510:512]=b'\x55\xaa'
        need(mbr==expected_mbr,'MBR layout/signature/unused entries')
        area=(stage/(BOARD+'-u-boot-with-spl.bin')).read_bytes()
        f.seek(SPL_OFFSET); need(f.read(len(area))==area,'disk bootarea differs from current staging')
        f.seek(512);need(not any(f.read(SPL_OFFSET-512)),'unexpected pre-SPL bytes')
        f.seek(SPL_OFFSET+len(area));need(not any(f.read(BOOT_OFFSET-SPL_OFFSET-len(area))),'unexpected bootloader/FAT gap')
    report['bootarea']=bootarea(area)
    need(area[:report['bootarea']['spl_bytes']]==(stage/(BOARD+'-spl.bin')).read_bytes(),'SPL staging mismatch')
    need(area[PROPER_OFFSET-SPL_OFFSET:]==(stage/(BOARD+'-u-boot.img')).read_bytes(),'proper staging mismatch')
    buildmeta=json.loads((stage/(BOARD+'-uboot-build.json')).read_text())
    need(buildmeta['sha256']==sha(area) and buildmeta['linux_cpus']==4 and buildmeta['source_ddr'] is True and buildmeta['vendor_ddr_or_monitor'] is False,'U-Boot build metadata')
    report['uboot_build']=buildmeta
    fat,rootfs=work/'boot.fat',work/'root.ext4'
    copy_region(raw,fat,BOOT_OFFSET,BOOT_BYTES)
    copy_region(raw,rootfs,ROOT_OFFSET,root_mib*MIB)
    with fat.open('rb') as f: bpb=f.read(512)
    need(bpb[54:62]==b'FAT16   ' and bpb[510:512]==b'\x55\xaa','FAT16 boot sector')
    need(struct.unpack_from('<H',bpb,11)[0]==512 and struct.unpack_from('<I',bpb,28)[0]==8192,'FAT geometry')
    report['fat_fsck']=checked([host_tool(source,'fsck.fat'),'-n',fat],env)
    fit,scr=work/'kernel.itb',work/'boot.scr'
    for name,dest in [('openwrt-t153.itb',fit),('boot.scr',scr)]:
        checked([host_tool(source,'mcopy'),'-i',fat,'::/'+name,dest],env)
    need(fit.read_bytes()==(kdir/(BOARD+'-kernel.bin')).read_bytes(),'FAT FIT differs from build FIT')
    zimage,report['fit']=fit_kernel(fit.read_bytes(),kdir)
    report['kernel']=persistent_kernel(zimage,kdir,source,work)
    script,stamp=legacy(scr.read_bytes(),6)
    command=(source/'target/linux/sunxi/image/t153.bootscript').read_bytes()
    need(script==struct.pack('>II',len(command),0)+command,'boot.scr differs from this source')
    need(stamp==epoch,'boot.scr SOURCE_DATE_EPOCH mismatch')
    need(b'root=PARTUUID=15302512-02' in command and b'rootfstype=ext4 rootwait rw' in command and b'${bootdev}:1 ${loadaddr} openwrt-t153.itb' in command,'boot.scr persistent boot arguments')
    report['boot_script']={'sha256':digest(scr),'timestamp':stamp,'partuuid':'15302512-02'}
    report['original_rootfs']=info(original_root)
    need(original_root.stat().st_size==root_mib*MIB,'build rootfs size mismatch')
    e2fsck=host_tool(source,'e2fsck')
    report['original_rootfs_fsck']=run([e2fsck,'-f','-n',original_root],env)
    initial=report['original_rootfs_fsck']
    need(initial['returncode'] in (0,4),'unexpected original ext4 fsck failure')
    if initial['returncode']==4:
        need('Padding at end of inode bitmap is not set.' in initial['output'],'unrecognized original ext4 error')
    normalized=work/'normalized.ext4'
    shutil.copyfile(original_root,normalized)
    report['normalization']=run([e2fsck,'-p','-f',normalized],env)
    need(report['normalization']['returncode'] in (0,1),'private ext4 normalization failed')
    report['normalized_rootfs_fsck']=checked([e2fsck,'-f','-n',normalized],env)
    report['final_rootfs']=info(rootfs)
    report['final_rootfs']['retained']=False
    report['final_rootfs']['disk_offset']=ROOT_OFFSET
    report['final_rootfs_fsck']=run([e2fsck,'-f','-n',rootfs],env)
    need(report['final_rootfs_fsck']['returncode']==0,'final image ext4 has filesystem errors: '+report['final_rootfs_fsck']['output'])
    need(digest(rootfs)==digest(normalized),'root partition differs from independently normalized build rootfs')
    report['rootfs_metadata_delta']=ext4_metadata_changes(original_root,rootfs)
    report['rootfs_relationship']='Private e2fsck normalization only; original build input preserved. Hash difference is disclosed, not claimed byte-identical.'
    report['installed_files']=installed_files(rootfs,rootdir,source,config)
    report['packages']=installed_packages(rootfs,rootdir,source,config,out,args.required_packages)
    report['aic8800d80']=aic_image_content(rootfs,rootdir,source,config)
    need(digest(original_root)==report['original_rootfs']['sha256'],'original rootfs changed during verification')
    checksums=out/'sha256sums'
    line=one((line for line in checksums.read_text().splitlines() if line.split(maxsplit=1)[-1].lstrip('*')==image.name),'image checksum entry')
    need(line.split()[0]==report['image']['sha256'],'published image checksum mismatch')
    report['checksums']=info(checksums)
    if args.raw_output:
        dest=args.raw_output.resolve()
        if dest.exists():
            need(dest.is_file() and digest(dest)==report['raw_image']['sha256'],'raw output already exists with different content')
        else:
            shutil.copyfile(raw,dest)
        report['raw_image']['path']=str(dest)
        report['raw_image']['retained']=True
    else:
        report['raw_image']['path']=None
        report['raw_image']['retained']=False
    report['status']='passed'


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--required-packages',type=Path,default=Path(__file__).with_name('required-packages.json'),
                    help='JSON packages list independently required in config, final manifest and image database')
    ap.add_argument('--image',type=Path)
    ap.add_argument('--rootfs-source',type=Path,help='Optional explicit root.ext4 source')
    ap.add_argument('--output',type=Path,required=True,help='JSON report outside the input source tree')
    ap.add_argument('--raw-output',type=Path,help='Retain validated decompressed image outside the source tree')
    args=ap.parse_args()
    source=args.source.resolve()
    for target in (args.output,args.raw_output):
        if target is None: continue
        need(not target.is_symlink(),'output must not be a symlink')
        dest=target.resolve()
        need(dest!=source and source not in dest.parents,'outputs must be outside the source tree')
        need(not dest.exists() or dest.is_file(),'output must be a regular file')
        dest.parent.mkdir(parents=True,exist_ok=True)
    if args.raw_output:
        need(args.output.resolve()!=args.raw_output.resolve(),'JSON and raw output must differ')
    report={'schema_version':1,'status':'failed','hardware_verified':False,
            'verifier':info(Path(__file__).resolve()),
            'created_utc':datetime.now(timezone.utc).isoformat()}
    try:
        base=args.raw_output.resolve().parent if args.raw_output else args.output.resolve().parent
        with tempfile.TemporaryDirectory(prefix='.t153-native-verify-',dir=base) as work:
            verify(args,report,Path(work))
    except Exception as exc:
        report['error']=str(exc)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'report':str(args.output.resolve()),
        'raw_sha256':report.get('raw_image',{}).get('sha256'),'error':report.get('error')},indent=2))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':
    raise SystemExit(main())
