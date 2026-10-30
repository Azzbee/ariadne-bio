FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c AS plugin
ARG GDS_VERSION=2.13.4
ARG GDS_SHA256=10e072f73992224f1159f246c9d6a89da5f3b3434aeffa5be42647edda13a8d8
RUN python -c "import hashlib,urllib.request; p='/tmp/gds.jar'; urllib.request.urlretrieve('https://github.com/neo4j/graph-data-science/releases/download/${GDS_VERSION}/neo4j-graph-data-science-${GDS_VERSION}.jar',p); actual=hashlib.sha256(open(p,'rb').read()).hexdigest(); assert actual == '${GDS_SHA256}', 'GDS checksum mismatch'"

FROM neo4j:5.26.0-community@sha256:5a015e53de1895e7eee1574ae0325cf8c4b89587222778108c594bdd45a474b5
COPY --from=plugin --chown=neo4j:neo4j /tmp/gds.jar /var/lib/neo4j/plugins/neo4j-graph-data-science.jar
ENV NEO4J_dbms_security_procedures_unrestricted=gds.* \
    NEO4J_dbms_security_procedures_allowlist=gds.*
