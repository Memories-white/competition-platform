FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    curl \
    vim \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install flask

RUN echo "Python Flask challenge - Create and run a Flask web application" > /root/README.txt

EXPOSE 5000

CMD ["/bin/bash", "-c", "echo 'Container ready. Create a Flask app and run it on port 5000'; tail -f /dev/null"]
