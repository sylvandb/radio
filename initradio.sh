#! /bin/sh
# /etc/init.d/radio
#
### BEGIN INIT INFO
# Provides: Radio / LCD date / time / ip address
# Required-Start: $remote_fs $syslog
# Required-Stop: $remote_fs $syslog
# Default-Start: 2 3 4 5
# Default-Stop: 0 1 6
# Short-Description: Control MPD
# Description: Radio / LCD date / time / ip address
### END INIT INFO


DAEMON=/home/pi/radio/radio.py
PIDFILE=/var/run/radio.pid

start() {
    echo "Starting Radio"
    start-stop-daemon --start --make-pidfile --pidfile $PIDFILE --exec $DAEMON -b
}

stop() {
    echo "Stopping Radio"
    start-stop-daemon --stop --pidfile $PIDFILE --retry 5
}

export HOME
case "$1" in
    start)
        start
    ;;
    stop)
        stop
    ;;
    restart|force-reload)
        stop
        sleep 1
        start
    ;;
    *)
        echo "Usage: /etc/init.d/radio {start|stop}"
        exit 1
    ;;
esac
exit 0

