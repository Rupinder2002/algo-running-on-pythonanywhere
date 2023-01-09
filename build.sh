cp ./remote_syslog /usr/local/bin
pip install -r requirements.txt
remote_syslog   -p 32860 --tls   -d logs2.papertrailapp.com   --pid-file=/var/run/remote_syslog.pid   /tmp/file.log