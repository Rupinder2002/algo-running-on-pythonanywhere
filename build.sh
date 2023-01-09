pip install -r requirements.txt
remote_syslog \
  -p 23374 --tls \
  -d logs.papertrailapp.com \
  --pid-file=/var/run/remote_syslog.pid \
  /tmp/file.log