FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    openssh-server \
    curl \
    vim \
    htop \
    net-tools \
    iptables \
    sudo \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir /var/run/sshd && \
    echo 'root:changeme' | chpasswd && \
    sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config

RUN echo "System Administration challenge - Configure SSH, manage users, set up firewall" > /root/README.txt

EXPOSE 22 80

CMD ["/bin/bash", "-c", "service ssh start && echo 'Container ready. Tasks: configure SSH, add users, set up firewall.'; tail -f /dev/null"]
