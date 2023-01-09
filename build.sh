pip install -r requirements.txt
cp ./remote_syslog /usr/local/bin
remote_syslog   -p 32860 --tls   -d logs2.papertrailapp.com   --pid-file=/var/run/remote_syslog.pid   /tmp/file.log