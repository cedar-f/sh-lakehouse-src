FROM unitycatalog/unitycatalog:v0.7.0
USER root
COPY R2CredentialGenerator.java /tmp/R2CredentialGenerator.java
RUN mkdir -p /opt/r2-classes \
 && javac -cp "$(cat server/target/classpath)" -d /opt/r2-classes /tmp/R2CredentialGenerator.java \
 && printf ':/opt/r2-classes' >> server/target/classpath
COPY start.sh /opt/start-r2.sh
RUN chmod +x /opt/start-r2.sh && chown -R unitycatalog:unitycatalog /opt/r2-classes etc/conf
USER unitycatalog
ENTRYPOINT ["/bin/bash", "/opt/start-r2.sh"]
