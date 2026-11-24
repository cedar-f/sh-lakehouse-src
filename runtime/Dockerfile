FROM eclipse-temurin:17-jdk-jammy
ENV DEBIAN_FRONTEND=noninteractive PYTHONPATH=/opt/lakehouse \
    PYSPARK_PYTHON=/usr/bin/python3 PYSPARK_DRIVER_PYTHON=/usr/bin/python3
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip git openssh-client ca-certificates curl sudo \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /tmp/requirements.txt
RUN curl -fsSL https://deb.nodesource.com/setup_22.x -o /tmp/node-setup.sh \
 && bash /tmp/node-setup.sh && apt-get install -y nodejs && rm -rf /var/lib/apt/lists/* \
 && npm install -g configurable-http-proxy@5.1.0
COPY labextension /opt/extension
RUN cd /opt/extension && npm install --no-audit --no-fund \
 && jupyter labextension build . \
 && mkdir -p /usr/local/share/jupyter/labextensions/@lakehouse/workspace \
 && cp -r labextension/. /usr/local/share/jupyter/labextensions/@lakehouse/workspace/
RUN useradd -m -u 1000 -s /bin/bash analyst \
 && mkdir -p /workspace /var/lib/lakehouse /opt/lakehouse /home/analyst/.ivy2 /home/analyst/.ssh \
 && chown -R analyst:analyst /workspace /var/lib/lakehouse /home/analyst
COPY . /opt/lakehouse/
RUN mkdir -p /tmp/lakehouse-resolver \
 && javac -d /tmp/lakehouse-resolver /opt/lakehouse/ResolveSparkPackages.java \
 && jar --create --file /opt/lakehouse/spark-package-resolver.jar -C /tmp/lakehouse-resolver . \
 && rm -rf /tmp/lakehouse-resolver
# Git checkouts under a restrictive host umask can contain root-only files.
# Keep image code root-owned, but readable/traversable by the runtime user.
RUN chmod -R a+rX /opt/lakehouse /usr/local/share/jupyter/labextensions/@lakehouse/workspace \
 && chmod 0755 /opt/lakehouse/git_askpass.py \
 && mkdir -p /etc/jupyter/jupyter_server_config.d /home/analyst/.ipython/profile_default/startup \
 && printf '{"ServerApp":{"jpserver_extensions":{"lakehouse_server":true}}}' > /etc/jupyter/jupyter_server_config.d/lakehouse.json \
 && cp /opt/lakehouse/startup.py /home/analyst/.ipython/profile_default/startup/00-lakehouse.py \
 && chown -R analyst:analyst /home/analyst/.ipython
USER analyst
WORKDIR /workspace
CMD ["bash", "/opt/lakehouse/start.sh", "notebook"]
