FROM python:3.13-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        binutils \
        ca-certificates \
        curl \
        file \
        gcc \
        gdb \
        git \
        iputils-ping \
        jq \
        libcap2-bin \
        make \
        netcat-openbsd \
        openssl \
        procps \
        python3-pip \
        socat \
        strace \
        unzip \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
