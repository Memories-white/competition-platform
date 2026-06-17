FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    openssh-server \
    vim \
    curl \
    net-tools \
    htop \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir /var/run/sshd && \
    echo 'root:password' | chpasswd && \
    sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config && \
    sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config

RUN echo "System administration challenge - Configure SSH and system services" > /root/README.txt

EXPOSE 22

CMD ["/bin/bash", "-c", "service ssh start; echo 'SSH ready on port 22. Connect: ssh root@localhost -p <host_port>'; tail -f /dev/null"]
