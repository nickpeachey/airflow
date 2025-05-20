#!/bin/bash
set -e
CLUSTER_NAME="airflow-spark"
NAMESPACE_MINIO="minio"
NAMESPACE_SPARK="spark-operator"
echo "🔧 Creating kind cluster..."
cat <<EOF | kind create cluster --name ${CLUSTER_NAME} --config=-
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    extraPortMappings:
      - containerPort: 30080
        hostPort: 8080
      - containerPort: 30081
        hostPort: 9000
  - role: worker
  - role: worker
EOF
echo "📦 Installing MinIO..."
kubectl create namespace $NAMESPACE_MINIO || true
helm repo add minio https://charts.min.io/ && helm repo update
helm install minio minio/minio \
  --namespace $NAMESPACE_MINIO \
  --set accessKey=minioadmin \
  --set secretKey=minioadmin \
  --set service.nodePort=30081 \
  --set service.type=NodePort \
  --set resources.requests.memory=256Mi \
  --set resources.requests.cpu=250m
echo "⏳ Waiting for MinIO..."
kubectl wait --for=condition=available --timeout=120s deployment/minio -n $NAMESPACE_MINIO
echo "📦 Installing Spark Operator..."
kubectl create namespace $NAMESPACE_SPARK || true
helm repo add spark-operator https://googlecloudplatform.github.io/spark-on-k8s-operator && helm repo update
helm install spark-operator spark-operator/spark-operator \
  --namespace $NAMESPACE_SPARK \
  --set sparkJobNamespace=default \
  --set enableWebhook=true \
  --set serviceAccounts.spark.name=spark
echo "📦 Installing Airflow..."
helm repo add apache-airflow https://airflow.apache.org && helm repo update
kubectl create secret generic git-creds \
  --from-literal=username="your-username" \
  --from-literal=password="your-github-token" \
  --namespace default || true
helm install airflow apache-airflow/airflow \
  -n default \
  -f airflow-values.yaml
echo "🔧 Creating RBAC for Spark..."
kubectl apply -f - <<EOF
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: spark-role-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: spark-operator-role
subjects:
  - kind: ServiceAccount
    name: spark
    namespace: default
EOF
echo "🔧 Creating Airflow RBAC for Spark CRD access..."
kubectl apply -f - <<EOF
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: airflow-role
  namespace: default
rules:
  - apiGroups: ["sparkoperator.k8s.io"]
    resources: ["sparkapplications"]
    verbs: ["create", "get", "list", "watch", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: airflow-rolebinding
  namespace: default
subjects:
  - kind: ServiceAccount
    name: airflow-worker
    namespace: default
roleRef:
  kind: Role
  name: airflow-role
  apiGroup: rbac.authorization.k8s.io
EOF
echo "✅ Setup complete!"
echo "Airflow UI → http://localhost:8080"
echo "MinIO UI → http://localhost:9000"
