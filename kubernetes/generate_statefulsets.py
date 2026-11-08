
from pathlib import Path

output = Path(__file__).parent / "storage-statefulsets.yaml"

documents = []

for i in range(1, 7):
    node = f"node{i}"

    documents.append(f"""
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: {node}
spec:
  serviceName: {node}
  replicas: 1
  selector:
    matchLabels:
      app: {node}
  template:
    metadata:
      labels:
        app: {node}
    spec:
      containers:
        - name: {node}
          image: distributed-storage:latest
          imagePullPolicy: Never
          command:
            - python
            - -m
            - uvicorn
            - app.main:app
            - --host
            - "0.0.0.0"
            - --port
            - "8000"
          ports:
            - containerPort: 8000
          env:
            - name: NODE_ID
              value: "{node}"
            - name: STORAGE_DIR
              value: "/data"
            - name: METADATA_URL
              value: "http://metadata:8000"
          volumeMounts:
            - name: storage-data
              mountPath: /data
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 15
            periodSeconds: 10
      volumes:
        - name: storage-data
          persistentVolumeClaim:
            claimName: {node}-pvc
""")

output.write_text(
    "\n---\n".join(doc.strip() for doc in documents) + "\n",
    encoding="utf-8",
)

print("SUCCESS: Created Kubernetes StatefulSet configuration")
print("StatefulSets: 6")
print("Persistent volumes: 6 existing PVCs")
print("Output:", output)
