FROM alpine:3.20.10
RUN apk add --no-cache busybox=1.36.1-r31 busybox-extras=1.36.1-r31 \
    && mkdir -p /var/www && printf ok > /var/www/health
EXPOSE 8080
CMD ["/bin/busybox-extras", "httpd", "-f", "-p", "8080", "-h", "/var/www"]
