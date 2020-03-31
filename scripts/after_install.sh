#!/usr/bin/env bash
sudo python3 -m pip install -r /webapps/loansbot/requirements.txt
sudo python3 -m pip install -r /webapps/loansbot/logging-requirements.txt
sudo python3 -m pip install -r /webapps/loansbot/shared-requirements.txt
source /home/ec2-user/secrets.sh
cd /webapps/loansbot/src
sudo -E /usr/local/bin/supervisord -c ../cfg/supervisor.conf || :
