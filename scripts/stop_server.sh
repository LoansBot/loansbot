#!/usr/bin/env bash
/usr/local/bin/supervisorctl stop all || :
sleep 1
killall python3
