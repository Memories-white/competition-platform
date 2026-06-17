FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    redis-server \
    redis-tools \
    curl \
    vim \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

RUN echo "Redis server setup challenge - Install and configure Redis with custom port" > /root/README.txt

EXPOSE 6379

CMD ["/bin/bash", "-c", "echo 'Container ready. Run: redis-server --port 6379'; tail -f /dev/null"]
