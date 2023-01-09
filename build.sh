pip install -r requirements.txt
dpkg -i remote-syslog2_0.21_amd64.deb
cp log_files.ymal /etc
remote_syslog -c /etc/log_files.yml

