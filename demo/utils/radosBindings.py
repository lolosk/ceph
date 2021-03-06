import rados
import re
import os
import time
import threading
import signal

CONF_DIR  = '/home/kostis/git/django/ceph/demo/utils'
CEPH_CONF = os.path.join(CONF_DIR, 'ceph.conf')
KEYRING   = os.path.join(CONF_DIR, 'ceph.client.admin.keyring')
POOL      = 'data'
TIMEOUT   = 2
cluster   = None


def _connect():
    global cluster
    try:
        new_cluster = rados.Rados(conffile=CEPH_CONF, conf=dict(keyring=KEYRING))
        new_cluster.connect(timeout=TIMEOUT)
        cluster = new_cluster
        print "*** Connection Established ***"
    except:
        try:
            new_cluster.shutdown()
        except:
            pass
        finally:
            cluster = None
            print "*** Could not establish connection ***"

def _test_connection():
    try:
        test_conn = rados.Rados(conffile=CEPH_CONF, conf=dict(keyring=KEYRING))
        test_conn.connect(timeout=TIMEOUT)
        print "*** Connection OK ***"
        return True
    except:
        print "*** Connection FAILED ***"
        return False
    finally:
        try:
            test_conn.shutdown()
        except:
            pass

def _maintain_connection(): 
    global cluster
    while True:
        time.sleep(20)
        if _test_connection():
            if cluster is None:
                _connect()
        else:
            if cluster is not None:
                try:
                    cluster.shutdown()
                except:
                    pass
                finally:
                    cluster = None
                    print "*** Shut down previous connection ***"
            
def connected(ret_type):
    def decorator(f):
        def wrapped(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except:
                return ret_type()
        return wrapped
    return decorator

@connected(ret_type=list)
def get_object_list(user):
    ioctx = cluster.open_ioctx(POOL)
    objects = []
    for obj in ioctx.list_objects(): # this looks REALLY bad :)
        obj_owner, obj_name = _parse_object_name(obj)
        if obj_owner == user:
            objects.append(obj_name)
    return objects

@connected(ret_type=str)
def get_data(user, obj):
    obj_name = create_object_name(user, obj)
    ioctx = cluster.open_ioctx(POOL)
    return ioctx.read(obj_name)

@connected(ret_type=bool)
def delete_object(user, obj):
    obj_name = create_object_name(user, obj)
    ioctx = cluster.open_ioctx(POOL)
    ioctx.remove_object(obj_name)
    return True

@connected(ret_type=bool)
def store_object(user, name, data):
    obj_name = create_object_name(user, name)
    ioctx = cluster.open_ioctx(POOL)
    ioctx.write_full(obj_name, str(data))
    return True

def _parse_object_name(obj_name):
    return obj_name.key.split(';')

def create_object_name(user, name):
    return str("%s;%s" % (user, name))

def exists(user, name):
    return name in get_object_list(user)

def is_valid_name(name):
    return bool(re.match(r'^[a-zA-Z0-9\-]+$', name))

# should probably never be used
def startup_cluster():
    from subprocess import call
    call(['start-ceph'])

_connect()
threading.Thread(target=_maintain_connection).start()

