from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.datasets import Dataset
from airflow.utils.dates import days_ago

# Define a dataset - this represents your MinIO file
minio_file_dataset = Dataset("s3://my-minio-bucket/sample.csv")

def upload_file_to_minio():
    """Simulate uploading a file to MinIO"""
    print("Uploading file to MinIO bucket...")
    print("File uploaded successfully to s3://my-minio-bucket/sample.csv")
    print("Dataset updated!")

def process_file():
    """Process the file from MinIO"""
    print("Processing file from MinIO...")
    print("File processed successfully!")

# Producer DAG - Creates/Updates the dataset
producer_dag = DAG(
    'dataset_file_producer',
    default_args={'start_date': days_ago(1)},
    description='Uploads files to MinIO and updates dataset',
    schedule='@daily',  # Runs daily
    catchup=False,
    tags=['dataset', 'minio', 'producer'],
)

upload_task = PythonOperator(
    task_id='upload_file',
    python_callable=upload_file_to_minio,
    outlets=[minio_file_dataset],  # This task updates the dataset
    dag=producer_dag,
)

# Consumer DAG - Triggered when dataset is updated
consumer_dag = DAG(
    'dataset_file_consumer',
    default_args={'start_date': days_ago(1)},
    description='Processes files when dataset is updated',
    schedule=[minio_file_dataset],  # Triggered by dataset updates
    catchup=False,
    tags=['dataset', 'minio', 'consumer'],
)

process_task = PythonOperator(
    task_id='process_file',
    python_callable=process_file,
    inlets=[minio_file_dataset],  # This task consumes the dataset
    dag=consumer_dag,
)
