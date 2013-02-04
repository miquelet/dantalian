from hitagifs.fuse3 import FUSE, Operations

from errno import ENOENT, EPERM, EINVAL
from sys import argv, exit

import logging
import os
import tempfile

from hitagifs import tree

__all__ = ['HitagiMount']
ATTRS = ('st_atime', 'st_ctime', 'st_mtime', 'st_uid', 'st_gid', 'st_mode',
         'st_nlink', 'st_size')


class HitagiMount(Operations):

    def __init__(self, root, tree):
        self.root = root
        self.tree = tree

    def chmod(self, path, mode):
        """chmod

        If `path` points beyond a node, forward the request to the OS (via
        built-in os module).  Otherwise the operation is invalid and raises
        EINVAL.
        """
        node, path = self._getnode(path)
        if path:
            os.chmod(_getpath(node, path), mode)
        else:
            raise OSError(EINVAL)

    def chown(self, path, uid, gid):
        """chown

        If `path` points beyond a node, forward the request to the OS (via
        built-in os module).  Otherwise the operation is invalid and raises
        EINVAL.
        """
        node, path = self._getnode(path)
        if path:
            os.chown(_getpath(node, path), uid, gid)
        else:
            raise OSError(EINVAL)

    def create(self, path, mode):
        """create

        If `path` points beyond a node, forward the request to the OS (via
        built-in os module).  Once a file is created, it is tagged with all of
        the tags of the furthest node and return the file's file descriptor.
        Otherwise the operation is invalid and raises EINVAL.
        """
        node, path = self._getnode(path)
        if path:
            t = list(node.tags)
            path = os.path.join(self.root.tagpath(t.pop(0)), *path)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT, mode)
            for tag in t:
                self.root.tag(path, tag)
            return fd
        else:
            raise OSError(EINVAL)

    def getattr(self, path, fh=None):
        """getattr

        If `path` points beyond a node, forward the request to the OS (via
        built-in os module).  Otherwise the operation is invalid and raises
        EINVAL.
        """
        node, path = self._getnode(path)
        if path:
            st = os.lstat(path)
            return dict((key, getattr(st, key)) for key in ATTRS)
        else:
            #st = os.stat(self.root.root)
            #    return dict(
            #        st_atime,
            #        st_ctime,
            #        st_mtime,
            #        st_uid=st.st_uid,
            #        st_gid=st.st_gid,
            #        st_mode=st.st_mode,
            #        st_nlink,
            #        st_size=st.st_size)
            raise OSError(EINVAL)

    def getxattr(self, path, name, position=0):
        """getxattr

        Not implemented.  Raises EPERM.
        """
        #attrs = self.files[path].get('attrs', {})
        #try:
        #    return attrs[name]
        #except KeyError:
        #    return ''       # Should return ENOATTR
        raise OSError(EPERM)

    def listxattr(self, path):
        """listxattr

        Not implemented.  Raises EPERM.
        """
        #attrs = self.files[path].get('attrs', {})
        #return attrs.keys()
        raise OSError(EPERM)

    def mkdir(self, path, mode):
        """mkdir

        If `path` points beyond a node, forward the request to the OS (via
        built-in os module).  Once a directory is created, it is converted and
        tagged with all of the tags of the furthest node.  Otherwise the
        operation is invalid and raises EINVAL.
        """
        node, path = self._getnode(path)
        if path:
            t = list(node.tags)
            path = os.path.join(self.root.tagpath(t.pop(0)), *path)
            fd = os.mkdir(path, mode)
            self.root.convert(path)
            for tag in t:
                self.root.tag(path, tag)
            return fd
        else:
            raise OSError(EINVAL)

    def open(self, path, flags):
        """open

        If `path` points beyond a node, forward the request to the OS (via
        built-in os module).  Otherwise the operation is invalid and raises
        EINVAL.
        """
        node, path = self._getnode(path)
        if path:
            return os.open(_getpath(node, path), flags)
        else:
            raise OSError(EINVAL)

    def read(self, path, size, offset, fh):
        """read

        `path` is ignored.  Forward the request to the OS (via built-in os
        module) with the file descriptor.
        """
        os.lseek(fh, offset, 0)
        return os.read(fh, size)

    def readdir(self, path, fh):
        """readdir

        If `path` points beyond a node, forward the request to the OS (via
        built-in os module).  Otherwise the result is generated as an empty
        directory plus others depending on the type of the furthest node.  If
        it is an FSNode, its children nodes are added.  If it is additionally a
        TagNode, its files are calculated according to its rules and added.
        """
        node, path = self._getnode(path)
        if path:
            return ['.', '..'] + os.lsdir(_getpath(node, path))
        else:
            return ['.', '..'] + [node[x] for x in iter(node)]

    def readlink(self, path):
        """readlink

        If `path` points beyond a node, forward the request to the OS (via
        built-in os module).  Otherwise the operation is invalid and raises
        EINVAL.
        """
        node, path = self._getnode(path)
        if path:
            return os.readlink(_getpath(node, path))
        else:
            raise OSError(EINVAL)

    def removexattr(self, path, name):
        """removexattr

        Not implemented.  Raises EPERM.
        """
        #attrs = self.files[path].get('attrs', {})
        #try:
        #    del attrs[name]
        #except KeyError:
        #    pass        # Should return ENOATTR
        raise OSError(EPERM)

    def rename(self, old, new):
        """rename

        This one is tricky.  If either path points to a node, raise EINVAL.  If
        `old` points only and not more than one directory deep beyond a node,
        all of that node's tags are removed from `old`.  If `new` points to a
        path not more than one directory deep beyond a node, all of that node's
        tags are added to `old`.  Whichever combination of the above, `old` is
        then renamed to `new` via built-in os module.
        """
        onode, opath = self._getnode(old)
        nnode, npath = self._getnode(new)
        if opath is None or npath is None:
            raise OSError(EINVAL)
        ofpath = _getpath(onode, opath)
        nfpath = _getpath(nnode, npath)
        if len(opath) > 1:
            pass
        else:
            ofpath = _tmplink(ofpath)
            for tag in list(onode.tags):
                self.root.untag(ofpath, tag)
        if len(npath) > 1:
            os.rename(ofpath, nfpath)
        else:
            for tag in list(nnode.tags):
                self.root.tag(ofpath, tag)
            os.rm(ofpath)

    def rmdir(self, path):
        """rmdir

        If `path` points beyond a node, forward the request to the OS (via
        built-in os module).  Otherwise the operation is invalid and raises
        EINVAL.
        """
        node, path = self._getnode(path)
        if path:
            os.rmdir(_getpath(node, path))
        else:
            raise OSError(EINVAL)

    def setxattr(self, path, name, value, options, position=0):
        """setxattr

        Not implemented.  Raises EPERM.
        """
        ## Ignore options
        #attrs = self.files[path].setdefault('attrs', {})
        #attrs[name] = value
        raise OSError(EPERM)

    def statfs(self, path):
        """statfs

        Forward the request to the OS (via built-in os module).
        """
        stv = os.statvfs(path)
        return dict((key, getattr(stv, key)) for key in (
            'f_bavail', 'f_bfree', 'f_blocks', 'f_bsize', 'f_favail',
            'f_ffree', 'f_files', 'f_flag', 'f_frsize', 'f_namemax'))

    def symlink(self, target, source):
        """symlink

        If `path` points beyond a node, forward the request to the OS (via
        built-in os module).  If `path` points not more than one directory deep
        beyond the node, add all of the node's tags to it.  Otherwise the
        operation is invalid and raises EINVAL.
        """
        node, path = self._getnode(source)
        if path:
            os.symlink(target, _getpath(node, path))
            if len(path) == 1:
                t = list(node.tags)
                for tag in t:
                    self.root.tag(_getpath(node, path), tag)
        else:
            raise OSError(EINVAL)

    def truncate(self, path, length, fh=None):
        """truncate

        If `path` points beyond a node, forward the request to the OS (via
        built-in os module).  Otherwise the operation is invalid and raises
        EINVAL.  `path` is used; `fh` is ignored.
        """
        node, path = self._getnode(path)
        if path:
            with open(_getpath(node, path), 'r+') as f:
                f.truncate(length)
        else:
            raise OSError(EINVAL)

    def unlink(self, path):
        """unlink

        If `path` points beyond a node, forward the request to the OS (via
        built-in os module).  Otherwise the operation is invalid and raises
        EINVAL.
        """
        node, path = self._getnode(path)
        if path:
            os.unlink(_getpath(node, path))
        else:
            raise OSError(EINVAL)

    def utimens(self, path, times=None):
        """utimens

        If `path` points beyond a node, forward the request to the OS (via
        built-in os module).  Otherwise the operation is invalid and raises
        EINVAL.
        """
        node, path = self._getnode(path)
        if path:
            os.utime(_getpath(node, path), times)
        else:
            raise OSError(EINVAL)

    def write(self, path, data, offset, fh):
        """write

        If `path` points beyond a node, forward the request to the OS (via
        built-in os module).  Otherwise the operation is invalid and raises
        EINVAL.  `fh` is used; `path` is ignored.
        """
        node, path = self._getnode(path)
        if path:
            os.lseek(fh, offset, 0)
            return os.write(fh, data)
        else:
            raise OSError(EINVAL)

    def _getnode(self, path):
        """Get node and path components

        path is a list of strings pointing to a path under the FUSE vfs.  If
        path is broken, raise OSError(ENOENT).

        Returns a tuple (cur, path).  cur is the furthest FSNode along the
        path.  path is a list of strings indicating the path from the given
        node.  If node is the last file in the path, path is None.
        """
        assert len(path) > 0
        path = _splitpath(path)
        cur = self.tree[path.pop(0)]
        while path:
            try:
                a = self.tree[path[0]]
            except KeyError:
                raise OSError(ENOENT)
            if isinstance(a, str):
                return (cur, path)
            else:
                cur = a
                del path[0]
        return (cur, None)


def _getpath(node, path):
    """Get real path

    Calculate and return the real path given TagNode `node` and list of strings
    `path`.  If `node` is not a TagNode, raise OSError(EINVAL).
    """
    if not isinstance(node, tree.TagNode):
        raise OSError(EINVAL)
    return os.path.join(node[path[0]], *path[1:])


def _splitpath(path):
    """Split path into list"""
    return os.path.split(path.lstrip('/'))


def _tmplink(target):
    while True:
        fh, path = tempfile.mkstemp()
        os.close(fh)
        os.remove(path)
        try:
            os.link(target, path)
        except FileExistsError:
            continue
        else:
            return path


if __name__ == "__main__":
    if len(argv) != 2:
        print('usage: %s <mountpoint>' % argv[0])
        exit(1)
    logging.getLogger().setLevel(logging.DEBUG)
    fuse = FUSE(HitagiMount(), argv[1], foreground=True)