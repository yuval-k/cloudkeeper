FROM debian:buster as build-env
ENV DEBIAN_FRONTEND=noninteractive
ARG TESTS
ARG SOURCE_COMMIT
ARG SUPERVISOR_VERSION=4.2.2
ARG BUSYBOX_VERSION=1.34.1
ARG ARANGODB_VERSION=3.8.1
ARG PROMETHEUS_VERSION=2.30.1

ENV PATH=/usr/local/db/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
# Install Build dependencies
RUN apt-get update
RUN apt-get -y install apt-utils
RUN apt-get -y install \
        build-essential \
        curl \
        python3 \
        python3-pip \
        pypy3 \
        pypy3-dev \
        rustc \
        shellcheck \
        findutils \
        libtool \
        automake \
        autoconf \
        libffi-dev \
        libssl-dev \
        cargo \
        linux-headers-amd64

# Download and install ArangoDB (graphdb)
WORKDIR /usr/local/db
RUN curl -L -o /tmp/arangodb.tar.gz https://download.arangodb.com/arangodb38/Community/Linux/arangodb3-linux-${ARANGODB_VERSION}.tar.gz
RUN tar xzvf /tmp/arangodb.tar.gz --strip-components=1 -C /usr/local/db

# Build and install Busybox
WORKDIR /build/busybox
RUN curl -L -o /tmp/busybox.tar.bz2 https://busybox.net/downloads/busybox-${BUSYBOX_VERSION}.tar.bz2
RUN tar xjvf /tmp/busybox.tar.bz2 --strip-components=1 -C /build/busybox
RUN make defconfig
RUN sed -i -e "s/^CONFIG_FEATURE_SYSLOGD_READ_BUFFER_SIZE=.*/CONFIG_FEATURE_SYSLOGD_READ_BUFFER_SIZE=2048/" .config
RUN make
RUN cp busybox /usr/local/bin/

# Download and install Prometheus (tsdb)
WORKDIR /usr/local/tsdb
RUN curl -L -o /tmp/prometheus.tar.gz  https://github.com/prometheus/prometheus/releases/download/v${PROMETHEUS_VERSION}/prometheus-${PROMETHEUS_VERSION}.linux-amd64.tar.gz
RUN tar xzvf /tmp/prometheus.tar.gz --strip-components=1 -C /usr/local/tsdb
COPY docker/prometheus.yml /usr/local/tsdb/prometheus.yml

# Prepare PyPy build env
RUN mkdir -p /build-pypy

# Download and install Python test tools
RUN python3 -m pip install --upgrade pip
RUN pypy3 -m pip install --upgrade pip
RUN rm -f /usr/local/bin/pip*
RUN python3 -m pip install tox flake8

# Build cklib
COPY cklib /usr/src/cklib
WORKDIR /usr/src/cklib
RUN if [ "X${TESTS:-false}" = Xtrue ]; then tox; fi
RUN python3 -m pip wheel -w /build -f /build .
RUN pypy3 -m pip wheel -w /build-pypy -f /build-pypy .

# Build ckcore
COPY ckcore /usr/src/ckcore
WORKDIR /usr/src/ckcore
#RUN if [ "X${TESTS:-false}" = Xtrue ]; then nohup bash -c "/usr/local/db/bin/arangod --database.directory /tmp --server.endpoint tcp://127.0.0.1:8529 --database.password root &"; sleep 5; tox; fi
RUN pypy3 -m pip wheel -w /build-pypy -f /build-pypy .

# Build cloudkeeperV1
COPY cloudkeeperV1 /usr/src/cloudkeeperV1
WORKDIR /usr/src/cloudkeeperV1
RUN if [ "X${TESTS:-false}" = Xtrue ]; then tox; fi
RUN python3 -m pip wheel -w /build -f /build .

# Build ckworker
COPY ckworker /usr/src/ckworker
WORKDIR /usr/src/ckworker
RUN if [ "X${TESTS:-false}" = Xtrue ]; then tox; fi
RUN python3 -m pip wheel -w /build -f /build .

# Build ckmetrics
COPY ckmetrics /usr/src/ckmetrics
WORKDIR /usr/src/ckmetrics
RUN if [ "X${TESTS:-false}" = Xtrue ]; then tox; fi
RUN python3 -m pip wheel -w /build -f /build .

# Build cksh
COPY cksh /usr/src/cksh
WORKDIR /usr/src/cksh
RUN if [ "X${TESTS:-false}" = Xtrue ]; then tox; fi
RUN python3 -m pip wheel -w /build -f /build .

# Build cloudkeeper plugins
COPY plugins /usr/src/plugins
WORKDIR /usr/src
RUN cd plugins/aws/ && pip wheel -w /build -f /build . && cd -
RUN if [ "X${TESTS:-false}" = Xtrue ]; then find plugins/ -name tox.ini | while read toxini; do cd $(dirname "$toxini") && tox && cd - || exit 1; done; fi
RUN find plugins/ -maxdepth 1 -mindepth 1 -type d -print0 | xargs -0 python3 -m pip wheel -w /build -f /build

# Build supervisor
RUN python3 -m pip wheel -w /build -f /build supervisor==${SUPERVISOR_VERSION}

# Install all wheels
RUN python3 -m pip install -f /build /build/*.whl
RUN pypy3 -m pip install -f /build-pypy /build-pypy/*.whl

# Copy image config and startup files
WORKDIR /usr/src/cloudkeeper
COPY docker/supervisor.conf.in /usr/local/etc/supervisor.conf.in
COPY docker/defaults /usr/local/etc/cloudkeeper/defaults
COPY docker/common /usr/local/etc/cloudkeeper/common
COPY docker/argsdispatcher /usr/local/bin/argsdispatcher
COPY docker/bootstrap /usr/local/sbin/bootstrap
COPY docker/bootstrap-graphdb /usr/local/sbin/bootstrap-graphdb
COPY docker/startup /usr/local/bin/startup
COPY docker/cksh-shim /usr/local/bin/cksh-shim
RUN chmod 755 /usr/local/bin/startup \
    /usr/local/bin/cksh-shim \
    /usr/local/sbin/bootstrap \
    /usr/local/sbin/bootstrap-graphdb
RUN if [ "${TESTS:-false}" = true ]; then \
        shellcheck -a -x -s bash -e SC2034 \
            /usr/local/sbin/bootstrap \
            /usr/local/bin/startup \
        ; \
    fi
COPY docker/dnsmasq.conf /usr/local/etc/dnsmasq.conf
COPY docker/supervisord.conf /usr/local/etc/supervisord.conf
RUN mkdir -p /usr/local/etc/supervisor/conf.d/
RUN chmod 640 /usr/local/etc/supervisord.conf
RUN echo "${SOURCE_COMMIT:-unknown}" > /usr/local/etc/git-commit.HEAD


# Setup main image
FROM debian:buster
ENV DEBIAN_FRONTEND=noninteractive
COPY --from=build-env /usr/local /usr/local
ENV PATH=/usr/sbin:/usr/bin:/sbin:/bin:/usr/local/db/bin:/usr/local/sbin:/usr/local/bin
WORKDIR /
RUN groupadd -g "${PGID:-0}" -o cloudkeeper \
    && useradd -g "${PGID:-0}" -u "${PUID:-0}" -o --create-home cloudkeeper \
    && apt-get update \
    && apt-get -y --no-install-recommends install apt-utils \
    && apt-get -y dist-upgrade \
    && apt-get -y --no-install-recommends install \
        python3-minimal \
        python3-pip \
        pypy3 \
        dumb-init \
        dnsmasq \
        libffi7 \
        openssl \
        procps \
        dateutils \
        curl \
        jq \
        cron \
        ca-certificates \
        openssh-client \
        locales \
        unzip \
    && echo 'LANG="en_US.UTF-8"' > /etc/default/locale \
    && echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen \
    && rm -f /bin/sh \
    && ln -s /bin/bash /bin/sh \
    && locale-gen \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3 1 \
    && mkdir -p /var/spool/cron/crontabs /var/run/cloudkeeper /var/log/supervisor \
    && ln -s /usr/local/bin/busybox /usr/local/sbin/syslogd \
    && ln -s /usr/local/bin/busybox /usr/local/sbin/mkpasswd \
    && ln -s /usr/local/bin/busybox /usr/local/bin/vi \
    && ln -s /usr/local/bin/busybox /usr/local/bin/patch \
    && ln -s /usr/local/bin/busybox /usr/local/bin/unix2dos \
    && ln -s /usr/local/bin/busybox /usr/local/bin/dos2unix \
    && ln -s /usr/local/bin/busybox /usr/local/bin/makemime \
    && ln -s /usr/local/bin/busybox /usr/local/bin/xxd \
    && ln -s /usr/local/bin/busybox /usr/local/bin/wget \
    && ln -s /usr/local/bin/busybox /usr/local/bin/less \
    && ln -s /usr/local/bin/busybox /usr/local/bin/lsof \
    && ln -s /usr/local/bin/busybox /usr/local/bin/httpd \
    && ln -s /usr/local/bin/busybox /usr/local/bin/ssl_client \
    && ln -s /usr/local/bin/busybox /usr/local/bin/ip \
    && ln -s /usr/local/bin/busybox /usr/local/bin/ipcalc \
    && ln -s /usr/local/bin/busybox /usr/local/bin/ping \
    && ln -s /usr/local/bin/busybox /usr/local/bin/ping6 \
    && ln -s /usr/local/bin/busybox /usr/local/bin/iostat \
    && ln -s /usr/local/bin/busybox /usr/local/bin/setuidgid \
    && ln -s /usr/local/bin/busybox /usr/local/bin/ftpget \
    && ln -s /usr/local/bin/busybox /usr/local/bin/ftpput \
    && ln -s /usr/local/bin/busybox /usr/local/bin/bzip2 \
    && ln -s /usr/local/bin/busybox /usr/local/bin/xz \
    && ln -s /usr/local/bin/busybox /usr/local/bin/pstree \
    && ln -s /usr/local/bin/busybox /usr/local/bin/killall \
    && ln -s /usr/local/bin/busybox /usr/local/bin/bc \
    && ln -s /usr/local/bin/cksh-shim /usr/bin/cksh \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

EXPOSE 8900 8529 9955 9090
VOLUME ["/data"]
ENTRYPOINT ["/usr/local/sbin/bootstrap"]
