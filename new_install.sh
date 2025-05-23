#!/bin/bash
set -e

echo "--- Starting the automated setup process ---"

# --- 1. Prerequisites Check ---
echo "1. Checking for required tools..."
command -v docker >/dev/null 2>&1 || { echo >&2 "Docker is required but not installed. Aborting."; exit 1; }
command -v kubectl >/dev/null 2>&1 || { echo >&2 "kubectl is required but not installed. Aborting."; exit 1; }
command -v helm >/dev/null 2>&1 || { echo >&2 "Helm is required but not installed. Aborting."; exit 1; }
command -v sbt >/dev/null 2>&1 || { echo >&2 "sbt (Scala Build Tool) is required but not installed. Aborting."; exit 1; }

echo "All required tools are installed."

# --- 2. Set up MinIO Locally ---
echo "2. Setting up MinIO locally using Docker..."

MINIO_DATA_DIR="$HOME/minio_data"
mkdir -p "$MINIO_DATA_DIR"

# Stop and remove existing MinIO container if it's running
if docker ps -a --format '{{.Names}}' | grep -q "minio_local"; then
  echo "Existing minio_local container found. Stopping and removing..."
  docker stop minio_local || true
  docker rm minio_local || true
fi

docker run -d -p 9000:9000 -p 9001:9001 \
  -v "$MINIO_DATA_DIR":/data \
  -e "MINIO_ROOT_USER=minioadmin" \
  -e "MINIO_ROOT_PASSWORD=minioadmin" \
  --name minio_local \
  quay.io/minio/minio server /data --console-address ":9001"

echo "MinIO container started. Access console at http://localhost:9001"
echo "Waiting for MinIO to be ready..."
sleep 10 # Give MinIO some time to start

# Install MinIO Client (mc) if not present
if ! command -v mc >/dev/null 2>&1; then
  echo "MinIO Client (mc) not found. Installing..."
  curl -LO https://dl.min.io/client/mc/release/linux-amd64/mc
  chmod +x mc
  sudo mv mc /usr/local/bin/mc
fi

# Configure mc client
mc alias set local-minio http://localhost:9000 minioadmin minioadmin --api S3v4

# Create bucket if it doesn't exist
if ! mc ls local-minio/airflow-logs >/dev/null 2>&1; then
  echo "Creating MinIO bucket 'airflow-logs'..."
  mc mb local-minio/airflow-logs
else
  echo "MinIO bucket 'airflow-logs' already exists."
fi

echo "MinIO setup complete."

# --- 3. Install Kubeflow Spark Operator ---
echo "3. Installing Kubeflow Spark Operator..."

kubectl create namespace spark-operator --dry-run=client -o yaml | kubectl apply -f - || true
helm repo add spark-operator https://kubeflow.github.io/spark-operator --force-update
helm repo update

helm install spark-operator spark-operator/spark-operator \
  --namespace spark-operator \
  --create-namespace \
  --set webhook.enable=true \
  --wait

kubectl create namespace spark-jobs --dry-run=client -o yaml | kubectl apply -f - || true
kubectl create serviceaccount spark -n spark-jobs --dry-run=client -o yaml | kubectl apply -f - || true
kubectl create clusterrolebinding spark-role-binding --clusterrole=edit --serviceaccount=spark-jobs:spark --namespace=spark-jobs --dry-run=client -o yaml | kubectl apply -f - || true

echo "Kubeflow Spark Operator installed and configured."

# --- 4. Prepare Kubernetes Secret for MinIO Credentials ---
echo "4. Creating Kubernetes Secret for MinIO credentials..."
kubectl create secret generic minio-credentials \
  --from-literal=access_key=minioadmin \
  --from-literal=secret_key=minioadmin \
  -n airflow --dry-run=client -o yaml | kubectl apply -f - || true

echo "Kubernetes Secret 'minio-credentials' created."

# --- 5. Build and Push Scala Spark Job Docker Image ---
echo "5. Building and pushing Scala Spark Job Docker Image..."

# Define your Docker Hub username
# IMPORTANT: Replace 'your-dockerhub-username' with your actual Docker Hub username
YOUR_DOCKERHUB_USERNAME="your-dockerhub-username" # <--- IMPORTANT: EDIT THIS LINE

if [ "$YOUR_DOCKERHUB_USERNAME" == "your-dockerhub-username" ]; then
  echo "ERROR: Please edit install.sh and set YOUR_DOCKERHUB_USERNAME to your actual Docker Hub username."
  exit 1
fi

# Create spark-scala-wordcount directory and files
mkdir -p spark-scala-wordcount/src/main/scala/com/example
cat <<EOF > spark-scala-wordcount/build.sbt
lazy val root = (project in file("."))
  .settings(
    name := "wordcount-app",
    version := "0.1.0-SNAPSHOT",
    scalaVersion := "2.12.17",
    libraryDependencies ++= Seq(
      "org.apache.spark" %% "spark-core" % "3.5.0" % "provided",
      "org.apache.spark" %% "spark-sql" % "3.5.0" % "provided"
    )
  )
addCompilerPlugin("org.typelevel" %% "kind-projector" % "0.13.2" cross CrossVersion.full)
addCompilerPlugin("com.olegpy" %% "better-monadic-for" % "0.3.1")
assemblyMergeStrategy in assembly := {
  case PathList("META-INF", xs @ _*) => MergeStrategy.discard
  case x => MergeStrategy.first
}
EOF

cat <<EOF > spark-scala-wordcount/src/main/scala/com/example/WordCount.scala
package com.example

import org.apache.spark.sql.SparkSession
import org.apache.spark.sql.functions._

object WordCount {
  def main(args: Array[String]): Unit = {
    if (args.length < 1) {
      println("Usage: WordCount <input_path> [output_path]")
      System.exit(1)
    }

    val inputPath = args(0)
    val outputPath = if (args.length > 1) args(1) else "/tmp/wordcount_output"

    val spark = SparkSession
      .builder()
      .appName("ScalaSparkWordCount")
      .getOrCreate()

    import spark.implicits._

    try {
      println(s"Reading input from: \$inputPath")
      val lines = spark.read.textFile(inputPath)
      val wordCounts = lines
        .flatMap(line => line.split("\\s+")) // Split by whitespace
        .filter(_.nonEmpty)
        .groupBy("value")
        .count()
        .withColumnRenamed("value", "word")
        .sort(desc("count"))

      println(s"Writing word counts to: \$outputPath")
      wordCounts.coalesce(1).write.mode("overwrite").csv(outputPath)
      println("Word count job completed successfully!")

    } catch {
      case e: Exception =>
        println(s"Error running Spark job: \${e.getMessage}")
        e.printStackTrace()
        System.exit(1)
    } finally {
      spark.stop()
    }
  }
}
EOF

cat <<EOF > spark-scala-wordcount/Dockerfile
# Use a base image with Spark and Java pre-installed
FROM bitnami/spark:3.5.0-debian-11-r0

# Set Spark Home environment variable (if not already set in base image)
ENV SPARK_HOME=/opt/bitnami/spark

# Create a directory for your application
WORKDIR /app

# Copy your fat JAR into the image
# The JAR name will be determined after sbt assembly
COPY target/scala-2.12/wordcount-app-assembly-0.1.0-SNAPSHOT.jar /app/wordcount-app.jar

# Define default command (optional, as Spark Operator will specify it)
# ENTRYPOINT ["/opt/bitnami/spark/bin/spark-submit"]
# CMD ["--class", "com.example.WordCount", "/app/wordcount-app.jar", "/opt/bitnami/spark/README.md", "/tmp/spark_output"]
EOF

echo "Building Scala Spark JAR..."
(cd spark-scala-wordcount && sbt clean assembly)

echo "Building Docker image for Spark job..."
docker build -t "$YOUR_DOCKERHUB_USERNAME/spark-wordcount:latest" spark-scala-wordcount

echo "Please log in to Docker Hub and push the image:"
echo "docker login"
echo "docker push $YOUR_DOCKERHUB_USERNAME/spark-wordcount:latest"
read -p "Press Enter after you have logged in and pushed the Docker image..."

echo "Spark job Docker image built and ready to be pushed."

# --- 6. Create Airflow DAG ---
echo "6. Creating Airflow DAG file..."

mkdir -p dags
cat <<EOF > dags/spark_wordcount_on_kubernetes.py
from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.spark_kubernetes import SparkKubernetesOperator
from airflow.providers.cncf.kubernetes.sensors.spark_kubernetes import SparkKubernetesSensor
from datetime import datetime, timedelta

# IMPORTANT: Replace 'your-dockerhub-username' with your actual Docker Hub username
YOUR_DOCKERHUB_USERNAME = "$YOUR_DOCKERHUB_USERNAME"

with DAG(
    dag_id='spark_wordcount_on_kubernetes',
    start_date=datetime(2023, 1, 1),
    schedule_interval=timedelta(days=1),
    catchup=False,
    tags=['spark', 'kubernetes', 'scala', 'minio'],
) as dag:
    # Define the SparkApplication YAML
    spark_app_yaml = f"""
apiVersion: sparkoperator.k8s.io/v1beta2
kind: SparkApplication
metadata:
  name: spark-wordcount-{{{{ ds_nodash }}}}
  namespace: spark-jobs # Namespace where Spark jobs will run
spec:
  type: Scala
  sparkVersion: "3.5.0"
  mode: cluster
  image: {YOUR_DOCKERHUB_USERNAME}/spark-wordcount:latest # Your Docker Hub image
  imagePullPolicy: Always
  mainApplicationFile: local:///app/wordcount-app.jar # Path to your JAR inside the Docker image
  mainClass: com.example.WordCount
  arguments:
    - "local:///opt/bitnami/spark/README.md" # Example input path (from Spark image)
    - "s3a://airflow-logs/wordcount-output/{{{{ ds_nodash }}}}" # Output path to MinIO
  hadoopConf:
    fs.s3a.impl: org.apache.hadoop.fs.s3a.S3AFileSystem
    fs.s3a.path.style.access: "true" # Required for MinIO
    fs.s3a.endpoint: "http://host.docker.internal:9000" # MinIO endpoint from Airflow pod perspective
    fs.s3a.connection.ssl.enabled: "false" # Disable SSL for local MinIO
    # Credentials are picked up from environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
    # which are injected into the Spark driver/executor pods by the Spark Operator
    # based on the serviceAccount and the Airflow configuration.
  driver:
    cores: 1
    memory: "1g"
    serviceAccount: spark # Service account created earlier
    labels:
      version: 3.5.0
  executor:
    cores: 1
    instances: 1
    memory: "1g"
    labels:
      version: 3.5.0
  restartPolicy:
    type: Never # Do not restart on failure; Airflow will handle retries
"""

    submit_spark_job = SparkKubernetesOperator(
        task_id='submit_wordcount_job',
        namespace='spark-jobs',
        application_file=spark_app_yaml,
        kubernetes_conn_id='kubernetes_default',
        do_xcom_push=True,
    )

    monitor_spark_job = SparkKubernetesSensor(
        task_id='monitor_wordcount_job',
        namespace='spark-jobs',
        application_name="{{ task_instance.xcom_pull(task_ids='submit_wordcount_job')['metadata']['name'] }}",
        kubernetes_conn_id='kubernetes_default',
    )

    submit_spark_job >> monitor_spark_job
EOF

echo "Airflow DAG 'spark_wordcount_on_kubernetes.py' created."

# --- 7. Deploy Airflow with MinIO Configuration ---
echo "7. Deploying Apache Airflow with MinIO remote logging configuration..."

kubectl create namespace airflow --dry-run=client -o yaml | kubectl apply -f - || true
helm repo add apache-airflow https://airflow.apache.org/charts --force-update
helm repo update

# Create airflow-values.yaml dynamically
cat <<EOF > airflow-values.yaml
executor: KubernetesExecutor

dags:
  gitSync:
    enabled: true
    repo: YOUR_GITHUB_REPO_URL # <--- IMPORTANT: Replace with your actual GitHub repo URL (where this script and dags/ are)
    branch: main
    # If your DAGs are in a subfolder within the repo:
    # subPath: dags

logs:
  persistence:
    enabled: true
  remoteLogging:
    enabled: true
    provider: S3
    s3:
      logBucket: "airflow-logs"
      endpoint: "http://host.docker.internal:9000"
      region: "us-east-1"
      extraConfigs:
        s3.addressing_style: "path"
        fs.s3a.impl: "org.apache.hadoop.fs.s3a.S3AFileSystem"
        fs.s3a.path.style.access: "true"
        fs.s3a.endpoint: "http://host.docker.internal:9000"
        fs.s3a.connection.ssl.enabled: "false"

extraEnv:
  - name: AIRFLOW_CONN_KUBERNETES_DEFAULT
    value: "kubernetes://?__extra__=%7B%22extra__kubernetes__in_cluster%22%3A+true%2C+%22extra__kubernetes__kube_config%22%3A+%22%22%2C+%22extra__kubernetes__kube_config_path%22%3A+%22%22%2C+%22extra__kubernetes__namespace%22%3A+%22%22%7D"
  - name: AWS_ACCESS_KEY_ID
    valueFrom:
      secretKeyRef:
        name: minio-credentials
        key: access_key
  - name: AWS_SECRET_ACCESS_KEY
    valueFrom:
      secretKeyRef:
        name: minio-credentials
        key: secret_key

webserver:
  extraEnv:
    - name: AIRFLOW_WEBSERVER_AUTH_USERNAME
      value: airflow
    - name: AIRFLOW_WEBSERVER_AUTH_PASSWORD
      value: airflow
EOF

# IMPORTANT: Update YOUR_GITHUB_REPO_URL in airflow-values.yaml manually after cloning this repo
echo "IMPORTANT: Before running 'helm install', please edit 'airflow-values.yaml' and replace 'YOUR_GITHUB_REPO_URL' with the URL of the GitHub repository where you will store these files (including the 'dags' folder)."
read -p "Press Enter after you have updated 'airflow-values.yaml' and committed it to your GitHub repo..."

helm upgrade --install airflow apache-airflow/airflow -f airflow-values.yaml --namespace airflow --wait

echo "Apache Airflow deployed successfully."

# --- 8. Final Instructions ---
echo "--- Setup Complete! ---"
echo "You can now access the Airflow UI:"
echo "1. Port-forward the Airflow webserver service:"
echo "   kubectl port-forward svc/airflow-webserver 8080:8080 -n airflow"
echo "2. Open your browser to http://localhost:8080"
echo "   Login with username: airflow, password: airflow"
echo ""
echo "Once in Airflow UI:"
echo " - The DAG 'spark_wordcount_on_kubernetes' should appear (it might take a few minutes for GitSync to pull)."
echo " - Enable the DAG and trigger it."
echo " - Monitor task logs. They should now be streamed to your local MinIO instance and visible in the Airflow UI."
echo ""
echo "To verify MinIO logs, you can use the 'mc' client:"
echo "mc ls local-minio/airflow-logs"
echo ""
echo "To stop MinIO:"
echo "docker stop minio_local"
