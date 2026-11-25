# Install dashboard nodes in the image, outside the bind-mounted /data directory.
FROM nodered/node-red:4.0.9
WORKDIR /usr/src/node-red
RUN npm install --omit=dev --no-audit --no-fund @flowfuse/node-red-dashboard@1.37.0
