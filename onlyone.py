import os
import fcntl
import __main__ as main


DEFAULT_NAME = os.path.basename(main.__file__)
_fp = {}


# if another instance is running,
#  will raise IOError: [Errno 11] Resource temporarily unavailable
# (other IOError's if unable to open the pid_file, e.g. permissions, path, etc)
def running(name=DEFAULT_NAME, path='/dev/shm', extension='.pid'):
    pid_file = '%s/%s%s' % (path, name, extension)
    try:
        fp = open(pid_file, 'r+')
    except IOError:
        fp = open(pid_file, 'w')
    try:
        fcntl.lockf(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        fp.close()
        raise
    fp.write('%d\n' % os.getpid())
    fp.truncate()
    _fp[name] = fp


# done running
def done(name=DEFAULT_NAME):
    if _fp.get(name):
        _fp[name].close()
        os.unlink(_fp[name].name)
        del _fp[name]


# check if 'me' is running
def me(name=DEFAULT_NAME):
    return bool(_fp.get(name))
