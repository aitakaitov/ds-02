#
# Node
#

FROM ghcr.io/maxotta/kiv-ds-docker:latest

COPY python /opt/node

RUN yum -q -y install python3
WORKDIR /opt/node
RUN pip3 install -r requirements.txt

CMD /usr/bin/python3 /opt/node/app.py

# EOF