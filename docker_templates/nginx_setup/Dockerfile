FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    nginx \
    curl \
    vim \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

RUN echo "Nginx setup challenge - Configure and start nginx" > /root/README.txt

EXPOSE 80

CMD ["/bin/bash", "-c", "echo 'Container ready. Run: service nginx start'; tail -f /dev/null"]
