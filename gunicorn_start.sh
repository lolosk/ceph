#!/bin/bash

NAME="ceph-demo"                       # Name of the application
DJANGODIR=/home/kostis/git/django/ceph # Django project directory
SOCKFILE=$DJANGODIR/run/gunicorn.sock  # we will communicte using this unix socket
USER=kostis                            # the user to run as
GROUP=kostis                           # the group to run as
NUM_WORKERS=9                          # how many worker processes should Gunicorn spawn
DJANGO_SETTINGS_MODULE=ceph.settings   # which settings file should Django use
DJANGO_WSGI_MODULE=ceph.wsgi           # WSGI module name

echo "Starting $NAME as `whoami`"

# Activate the virtual environment
cd $DJANGODIR
source ../venv/bin/activate
export DJANGO_SETTINGS_MODULE=$DJANGO_SETTINGS_MODULE
export PYTHONPATH=$DJANGODIR:$PYTHONPATH

# Create the run directory if it doesn't exist
RUNDIR=$(dirname $SOCKFILE)
test -d $RUNDIR || mkdir -p $RUNDIR

# Start your Django Unicorn
# Programs meant to be run under supervisor should not daemonize themselves (do not use --daemon)
exec gunicorn ${DJANGO_WSGI_MODULE}:application \
  --name $NAME \
  --workers $NUM_WORKERS \
  --user=$USER --group=$GROUP \
  --bind=unix:$SOCKFILE \
  --config gunicorn_config.py \
  --log-level=debug \
  --log-file=-
