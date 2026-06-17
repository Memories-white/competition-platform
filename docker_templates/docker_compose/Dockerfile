FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    curl \
    vim \
    net-tools \
    gnupg \
    lsb-release \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null && \
    apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin && \
    rm -rf /var/lib/apt/lists/*

RUN echo "Docker Compose challenge - Deploy a multi-service application using Docker Compose" > /root/README.txt

CMD ["/bin/bash", "-c", "echo 'Container ready. Deploy services with docker-compose.'; tail -f /dev/null"]
