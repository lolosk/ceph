import rados
import re
import time
import threading
import signal

CEPH_CONF = 'demo/utils/ceph.conf'
KEYRING   = 'demo/utils/ceph.client.admin.keyring'
POOL      = 'data'
TIMEOUT   = 2
cluster   = None


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

def _connect(): 
    global cluster
    while True:
        if _test_connection():
            if cluster is None:
                try:
                    new_cluster = rados.Rados(conffile=CEPH_CONF, conf=dict(keyring=KEYRING))
                    new_cluster.connect(timeout=TIMEOUT)
                    cluster = new_cluster
                    print "*** Connection Established ***"
                except:
                    print "*** Could not establish connection ***"
        else:
            if cluster is not None:
                try:
                    cluster.shutdown()
                finally:
                    cluster = None
                    print "*** Shut down previous connection ***"
        time.sleep(20)
            
threading.Thread(target=_connect).start()

def connected(ret_type):
    def decorator(f):
        def wrapped(*args, **kwargs):
            try:
                print "*** Submitting Query ***"
                ret = f(*args, **kwargs)
                print "*** Query succeeded ***"
                return ret
            except:
                print "*** Query failed ***"
                return ret_type()
        return wrapped
    return decorator

@connected(ret_type=list)
def get_object_list():
    ioctx = cluster.open_ioctx(POOL)
    return [o.key for o in ioctx.list_objects()]

@connected(ret_type=str)
def get_data(obj):
    ioctx = cluster.open_ioctx(POOL)
    return ioctx.read(str(obj))

@connected(ret_type=bool)
def delete_object(obj):
    ioctx = cluster.open_ioctx(POOL)
    ioctx.remove_object(str(obj))
    return True

@connected(ret_type=bool)
def store_object(name, data):
    ioctx = cluster.open_ioctx(POOL)
    ioctx.write_full(str(name), str(data))
    return True

def exists(name):
    return name in get_object_list()

def is_valid_name(name):
    return bool(re.match(r'^[a-zA-Z0-9\-]+$', name))

# should probably never be used
def startup_cluster():
    from subprocess import call
    call(['start-ceph'])

