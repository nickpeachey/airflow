#!/bin/bash

set -euo pipefail

CLUSTER_NAME="airflow-spark"
NAMESPACE="default"

echo "🧹 Cleaning up previous cluster (if any)..."
kind delete cluster --name "$CLUSTER_NAME" || true

echo "🚀 Creating kind cluster with resource constraints..."
cat <<EOF | kind create cluster --name "$CLUSTER_NAME" --config=-
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
  kubeadmConfigPatches:
    - |
      kind: InitConfiguration
      nodeRegistration:
        kubeletExtraArgs:
          system-reserved: "cpu=500m,memory=512Mi"
          kube-reserved: "cpu=500m,memory=512Mi"
  extraPortMappings:
    - containerPort: 30080  # Airflow Web UI
      hostPort: 8080
    - containerPort: 9000   # MinIO
      hostPort: 9000
EOF

echo "📦 Adding Helm repos..."

helm repo update

echo "📦 Installing localstack with resource constraints..."
# helm install minio minio/minio \
#   --namespace "$NAMESPACE" --create-namespace \
#   --set accessKey=minioadmin \
#   --set secretKey=minioadmin \
#   --set persistence.enabled=false \
#   --set resources.requests.memory=128Mi \
#   --set resources.requests.cpu=100m \
#   --set resources.limits.memory=512Mi \
#   --set resources.limits.cpu=500m \
#   --set mode=standalone

echo "🔑 Generating Fernet key..."
FERNET_KEY="Q1B3JHzxg7rCNXr1oGqKKoHTBzN8YMBEDlvp0a2rLR8="

echo "📦 Installing Airflow with guaranteed webserver..."

helm repo add localstack https://helm.localstack.cloud

helm repo update

kubectl create namespace localstack

helm install localstack localstack/localstack \
  --namespace localstack \
  --set service.type=ClusterIP \
  --set startServices="s3" \
  --set extraEnvVars[0].name=DEBUG \
  --set extraEnvVars[0].value=1


kubectl get svc -n localstack

kubectl port-forward svc/localstack 4566:4566 -n localstack
# helm upgrade --install airflow apache-airflow/airflow \
#   --namespace "$NAMESPACE" \
#   --set executor=KubernetesExecutor \
#   --set webserver.enabled=true \
#   --set webserver.service.type=NodePort \
#   --set webserver.service.nodePort=30080 \
#   --set webserver.defaultUser.enabled=true \
#   --set webserver.defaultUser.username=admin \
#   --set webserver.defaultUser.password=admin \
#   --set scheduler.enabled=true \
#   --set workers.enabled=false \
#   --set createUserJob.useHelmHooks=true \
#   --set createUserJob.applyCustomEnv=true \
#   --set env[0].name=AIRFLOW__CORE__FERNET_KEY \
#   --set env[0].value="$FERNET_KEY" \
#   --wait
helm upgrade --install airflow apache-airflow/airflow -n default -f values.yaml --debug --timeout 1m02s

echo "📦 Installing Spark Operator..."
helm upgrade --install spark-operator spark-operator/spark-operator \
  --namespace "$NAMESPACE" \
  --set sparkJobNamespace="$NAMESPACE" \
  --set webhook.enable=true \
  --set enableWebhook=true \
  --wait

echo "✅ Setup complete!"
echo "🌐 Airflow UI: http://localhost:8080"
echo "   Username: admin"
echo "   Password: admin"
