FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    mysql-server \
    mysql-client \
    curl \
    vim \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

RUN echo "MySQL configuration challenge - Install and configure MySQL, create a database" > /root/README.txt

EXPOSE 3306

CMD ["/bin/bash", "-c", "echo 'Container ready. Start MySQL and create database.'; tail -f /dev/null"]
