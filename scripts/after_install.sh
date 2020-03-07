#!/usr/bin/env bash
sudo python3 -m pip install -r /webapps/loansbot/requirements.txt
sudo python3 -m pip install -r /webapps/loansbot/logging-requirements.txt
source /home/ec2-user/secrets.sh
cd /webapps/reddit-proxy/src
sudo -E /usr/local/bin/supervisord -c ../cfg/supervisor.conf || :
