
from pathlib import Path

OUTPUT = Path(__file__).parent / "storage-nodes.yaml"

documents = []

for i in range(1, 7):
    node = f"node{i}"

    # Persistent storage for each node
    documents.append(f"""
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {node}-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 2Gi
""")

    # Storage node application
    documents.append(f"""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {node}
spec:
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
            tcpSocket:
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
      volumes:
        - name: storage-data
          persistentVolumeClaim:
            claimName: {node}-pvc
""")

   
    documents.append(f"""
apiVersion: v1
kind: Service
metadata:
  name: {node}
spec:
  selector:
    app: {node}
  ports:
    - port: 8000
      targetPort: 8000
  type: ClusterIP
""")

OUTPUT.write_text(
    "\n---\n".join(doc.strip() for doc in documents) + "\n",
    encoding="utf-8"
)

print(f"Created: {OUTPUT}")
print("Generated 6 deployments, 6 services, and 6 PVCs")
