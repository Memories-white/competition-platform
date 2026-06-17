FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    curl \
    vim \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

RUN echo "Node.js Express challenge - Build and run an Express.js web server" > /root/README.txt

EXPOSE 3000

CMD ["/bin/bash", "-c", "echo 'Container ready. Run: npm init && npm install express'; tail -f /dev/null"]
