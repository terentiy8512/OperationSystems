#!/usr/bin/env python3
# Name: Vadim Reger
# UPI: vreg113
# ID: 262767078

import logging
import os
import threading
import subprocess
import sys
import copy

from collections import defaultdict
from errno import ENOENT, ENODATA
from stat import S_IFDIR, S_IFLNK, S_IFREG
from time import time

from fuse import FUSE, FuseOSError, Operations, LoggingMixIn

class Memory(LoggingMixIn, Operations):
    'Example memory filesystem. Supports only one level of files.'

    last_modified_operations = []
    redo_list = []
    exec_mode = "normal"

    def __init__(self):
        self.files = {}
        self.data = defaultdict(bytes)
        self.fd = 0
        now = time()
        self.files['/'] = dict(
            st_mode=(S_IFDIR | 0o755),
            st_ctime=now,
            st_mtime=now,
            st_atime=now,
            st_size=0,
            st_nlink=2,
            )

    def chmod(self, path, mode):
        # Undo
        if Memory.exec_mode == "normal":
            Memory.last_modified_operations += [["chmod", self.files[path]['st_mode'], self.files[path]['st_ctime'], path]]
        # ----
        self.files[path]['st_mode'] &= 0o770000
        self.files[path]['st_mode'] |= mode
        self.files[path]['st_ctime'] = time()
        # Redo
        if Memory.exec_mode == "normal":
            Memory.redo_list += [["chmod", self.files[path]['st_mode'], self.files[path]['st_ctime'], path]]
        # ----
        return 0

    def chown(self, path, uid, gid):
        # Undo
        if Memory.exec_mode == "normal":
            Memory.last_modified_operations += [["chown", self.files[path], path]]
        # ----
        self.files[path]['st_uid'] = uid
        self.files[path]['st_gid'] = gid
        self.files[path]['st_ctime'] = time()
        # Redo
        if Memory.exec_mode == "normal":
            Memory.redo_list += [["chown", self.files[path], path]]
        # ----

    def create(self, path, mode):
        # Undo
        if Memory.exec_mode == "normal":
            Memory.last_modified_operations += [["create", path]]
        # -----
        now = time()
        self.files[path] = dict(
            st_mode=(S_IFREG | mode),
            st_uid=os.getuid(),
            st_gid=os.getgid(),
            st_nlink=1,
            st_size=0,
            st_ctime=now,
            st_mtime=now,
            st_atime=now,
            )
        self.data[path] = b''
        self.fd += 1
        self.files['/']['st_size'] += sys.getsizeof(self.files[path])
        # Redo
        if Memory.exec_mode == "normal":
            Memory.redo_list += [["create", self.data[path], self.files[path], path]]
        # -----
        return self.fd

    def getattr(self, path, fh=None):
        if path not in self.files:
            raise FuseOSError(ENOENT)
        return self.files[path]

    def getxattr(self, path, name, position=0):
        attrs = self.files[path].get('attrs', {})
        try:
            return attrs[name]
        except KeyError:
            raise FuseOSError(ENODATA)

    def listxattr(self, path):
        attrs = self.files[path].get('attrs', {})
        return attrs.keys()

    def mkdir(self, path, mode):
        # Undo
        if Memory.exec_mode == "normal":
            Memory.last_modified_operations += [["mkdir", path]]
        # ----
        now = time()
        self.files[path] = dict(
            st_mode=(S_IFDIR | mode),            
            st_uid=os.getuid(),
            st_gid=os.getgid(),
            st_nlink=2,
            st_size=0,
            st_ctime=now,
            st_mtime=now,
            st_atime=now,
            )
        self.files['/']['st_nlink'] += 1
        self.files['/']['st_size'] += sys.getsizeof(self.files[path])

        # Redo
        if Memory.exec_mode == "normal":
            Memory.redo_list += [["mkdir", self.files[path], path]]
        # ----


    def open(self, path, flags):
        self.files[path]['st_atime'] = time()
        self.fd += 1
        return self.fd

    def read(self, path, size, offset, fh):
        self.files[path]['st_atime'] = time()
        return self.data[path][offset:offset + size]

    def readdir(self, path, fh):
        self.files[path]['st_atime'] = time()
        return ['.', '..'] + [x[1:] for x in self.files if x != '/']

    def readlink(self, path):
        self.files[path]['st_atime'] = time()
        return self.data[path]

    def removexattr(self, path, name):
        attrs = self.files[path].get('attrs', {})

        try:
            del attrs[name]
        except KeyError:
            pass        # Should return ENOATTR

    def rename(self, old, new):
        # Undo
        if Memory.exec_mode == "normal":
            Memory.last_modified_operations += [["rename", self.data[old], self.files[old], old, new]]
        # ----
        self.data[new] = self.data.pop(old)
        self.files[new] = self.files.pop(old)
        self.files[new]['st_ctime'] = time()
        # Redo
        if Memory.exec_mode == "normal":
            Memory.redo_list += [["rename", self.data[new], self.files[new], old, new]]
        # ----

    def rmdir(self, path):
        # Undo
        if Memory.exec_mode == "normal":
            Memory.last_modified_operations += [["rmdir", self.files[path], path]]
        # ----
        # with multiple level support, need to raise ENOTEMPTY if contains any files
        self.files['/']['st_size'] -= sys.getsizeof(self.files[path])
        self.files.pop(path)
        self.files['/']['st_nlink'] -= 1
        # Redo
        if Memory.exec_mode == "normal":
            Memory.redo_list += [["rmdir", path]]
        # ----
        

    def setxattr(self, path, name, value, options, position=0):
        # Ignore options
        attrs = self.files[path].setdefault('attrs', {})
        attrs[name] = value

    def statfs(self, path):
        return dict(f_bsize=512, f_blocks=4096, f_bavail=2048)

    def symlink(self, target, source):
        # Undo
        if Memory.exec_mode == "normal":
            Memory.last_modified_operations += [["symlink", target]]
        # ----
        now = time()
        self.files[target] = dict(
            st_mode=(S_IFLNK | 0o777),
            st_nlink=1,
            st_uid=os.getuid(),
            st_gid=os.getgid(),
            st_size=len(source),
            st_ctime=now,
            st_mtime=now,
            st_atime=now)

        self.data[target] = source
        self.files['/']['st_size'] += sys.getsizeof(self.files[target])
        # Redo
        if Memory.exec_mode == "normal":
            Memory.redo_list += [["symlink", self.files[target], self.data[target], target]]
        # ----

    def truncate(self, path, length, fh=None):
        # Undo
        if Memory.exec_mode == "normal":
            Memory.last_modified_operations += [["truncate", copy.copy(self.data[path]), self.files[path], path]]
        # -----
        # make sure extending the file fills in zero bytes
        self.data[path] = self.data[path][:length].ljust(
            length, '\x00'.encode('ascii'))
        self.files[path]['st_size'] = length

    def unlink(self, path):
        # Undo
        if Memory.exec_mode == "normal":
            Memory.last_modified_operations += [["unlink", self.data[path], self.files[path], path]]
        # ----
        self.files['/']['st_size'] -= sys.getsizeof(self.files[path])
        self.data.pop(path)
        self.files.pop(path)
        # Redo
        if Memory.exec_mode == "normal":
            Memory.redo_list += [["unlink", path]]
        # ----

    def utimens(self, path, times=None):
        now = time()
        atime, mtime = times if times else (now, now)
        self.files[path]['st_atime'] = atime
        self.files[path]['st_mtime'] = mtime

    def write(self, path, data, offset, fh):
        # Undo 
        if Memory.exec_mode == "normal":
            Memory.last_modified_operations += [["write", copy.copy(self.data[path]), copy.copy(self.files[path]), path]]
        # ----

        self.data[path] = (
            # make sure the data gets inserted at the right offset
            self.data[path][:offset].ljust(offset, '\x00'.encode('ascii'))
            + data
            # and only overwrites the bytes that data is replacing
            + self.data[path][offset + len(data):])
        self.files[path]['st_size'] = len(self.data[path])
        self.files[path]['st_mtime'] = time()
        # Redo 
        if Memory.exec_mode == "normal":
            Memory.redo_list += [["write", copy.copy(self.data[path]), copy.copy(self.files[path]), path]]
        # ----
        return len(data)
    
    # Undo fuction
    def undo(self):
        Memory.exec_mode = "undo"
        my_list = list(Memory.last_modified_operations)
        if (my_list[0][0] == "create"):
            my_list.reverse()

        data_to_restore_if_truncate = None
        for element in my_list:
            if (element[0] == "create"):
                self.unlink(element[1])
                
            if (element[0] == "truncate"):
                data_to_restore_if_truncate = element[1]

            if (element[0] == "write"):
                if data_to_restore_if_truncate != None:
                    self.truncate(element[3], len(data_to_restore_if_truncate))
                    self.files[element[3]]['st_size'] = len(data_to_restore_if_truncate)
                    self.data[element[3]] = data_to_restore_if_truncate
                    self.files[element[3]]['st_mtime'] = element[2]['st_mtime']
                else:
                    self.truncate(element[3], len(element[1]))
                    self.files[element[3]]['st_size'] = len(element[1])
                    self.files[element[3]]['st_mtime'] = element[2]['st_mtime']
                    self.data[element[3]] = element[1]

            if (element[0] == "unlink"):
                self.files[element[3]] = element[2]
                self.data[element[3]] = element[1]
                self.files['/']['st_size'] += sys.getsizeof(element[2])

            if (element[0] == "symlink"):
                self.unlink(element[1])

            if (element[0] == "mkdir"):
                self.rmdir(element[1])

            if (element[0] == "rmdir"):
                self.files[element[2]] = element[1]
                self.files['/']['st_nlink'] += 1
                self.files['/']['st_size'] += sys.getsizeof(element[1])

            if (element[0] == "rename"):
                self.data[element[3]] = self.data.pop(element[4])
                self.files[element[3]] = self.files.pop(element[4])
                self.files[element[3]]['st_ctime'] = element[2]['st_ctime']

            if (element[0] == "chown"):
                self.files[element[2]]['st_uid'] = element[2]['st_uid']
                self.files[element[2]]['st_gid'] = element[2]['st_gid']
                self.files[element[2]]['st_ctime'] = element[2]['st_ctime']

            if (element[0] == "chmod"):
                self.files[element[3]]['st_mode'] = element[1]
                self.files[element[3]]['st_ctime'] = element[2]

        Memory.exec_mode = "normal"
        counter = 0

    # Redo function
    def redo(self):
        Memory.exec_mode = "redo"
        my_list = list(Memory.redo_list)
        for element in my_list:
            if (element[0] == "create"):
                self.files[element[3]] = element[2]
                self.data[element[3]] = element[1]
                self.files['/']['st_size'] += sys.getsizeof(element[2])

            if (element[0] == "write"):
                self.truncate(element[3], len(element[1]))
                self.files[element[3]]['st_size'] = len(element[1])
                self.files[element[3]]['st_mtime'] = element[2]['st_mtime']
                self.data[element[3]] = element[1]

            if (element[0] == "unlink"):
                self.unlink(element[1])

            if (element[0] == "symlink"):
                self.files[element[3]] = element[1]
                self.data[element[3]] = element[2]
                self.files['/']['st_size'] += sys.getsizeof(self.files[element[3]])

            if (element[0] == "mkdir"):
                self.files[element[2]] = element[1]
                self.files['/']['st_nlink'] += 1
                self.files['/']['st_size'] += sys.getsizeof(element[1])

            if (element[0] == "rmdir"):
                self.rmdir(element[1])

            if (element[0] == "rename"):
                self.data[element[4]] = self.data.pop(element[3])
                self.files[element[4]] = self.files.pop(element[3])
                self.files[element[4]]['st_ctime'] = element[2]['st_ctime']

            if (element[0] == "chown"):
                self.files[element[2]]['st_uid'] = element[2]['st_uid']
                self.files[element[2]]['st_gid'] = element[2]['st_gid']
                self.files[element[2]]['st_ctime'] = element[2]['st_ctime']

            if (element[0] == "chmod"):
                self.files[element[3]]['st_mode'] = element[1]
                self.files[element[3]]['st_ctime'] = element[2]

        Memory.exec_mode = "normal"


def receive_undo_request():
    carry_on = True
    state_change = True
    prev_undo_list = []
    prev_redo_list = []
    while carry_on:
        
        command = input ("undoshell: ")
        
        if command == "undo":
            if(len(memory_fs.last_modified_operations) != 0):
                memory_fs.undo()
                state_change = False
            else:
                print("undo not possible")

        elif command == "redo":
            
            if (state_change == False):
                memory_fs.redo()
                state_change = False
            else:
                print("redo not possible")
            

        elif command == "quit":
            print ("Shutting down user space file system.")
            os.system("fusermount -u memdir")
            carry_on = False
        else:

            prev_undo_list = list(memory_fs.last_modified_operations)
            prev_redo_list = list(memory_fs.redo_list)

            subprocess.run(command, shell=True, cwd="memdir")

            if(prev_undo_list != memory_fs.last_modified_operations):
                for element in prev_undo_list:
                    memory_fs.last_modified_operations.pop(memory_fs.last_modified_operations.index(element))
                for element in prev_redo_list:
                    memory_fs.redo_list.pop(memory_fs.redo_list.index(element))
                state_change = True

                

            
            

if __name__ == '__main__':
    base_dir = os.getcwd()
    memory_fs = Memory()
    threading.Thread(target=receive_undo_request).start()
    logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)
    fuse = FUSE(memory_fs, "memdir", foreground=True, allow_other=False)
