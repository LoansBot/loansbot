#!/usr/bin/env bash
sudo yum -y install python3 make glibc-devel gcc patch python3-devel libcurl4-gnutls-dev libxml2-dev libssl-dev postgresql-common postgresql-devel postgresql-client
sudo python3 -m pip install --upgrade pip
sudo python3 -m pip install supervisor
sudo /usr/local/bin/supervisorctl stop all || :
sudo pkill -F /webapps/loansbot/src/supervisord.pid || :
rm -rf /webapps/loansbot/src
rm -rf /webapps/loansbot/scripts
rm -rf /webapps/loansbot/cfg
rm -f /webapps/loansbot/requirements.txt
rm -f /webapps/loansbot/logging-requirements.txt