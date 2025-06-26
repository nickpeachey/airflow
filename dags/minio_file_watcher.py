import os
import boto3
from datetime import datetime, timedelta
from airflow import DAG
from airflow.hooks.base import BaseHook
from airflow.operators.python import PythonSensor, PythonOperator

# Custom sensor function to check for new/changed files in MinIO

def minio_file_change_sensor(**kwargs):
    """
    Sensor function to detect new or changed files in a MinIO bucket.
    Stores the last seen file list in XCom for change detection.
    """
    # Get MinIO connection from Airflow
    conn = BaseHook.get_connection('minio_conn')
    minio_endpoint = conn.host
    minio_access_key = conn.login
    minio_secret_key = conn.password
    bucket_name = 'my-minio-bucket'

    # Ensure endpoint is a full URL
    if not (minio_endpoint.startswith('http://') or minio_endpoint.startswith('https://')):
        minio_endpoint = f'http://{minio_endpoint}:9000'

    # Connect to MinIO using boto3
    s3 = boto3.client(
        's3',
        endpoint_url=minio_endpoint,
        aws_access_key_id=minio_access_key,
        aws_secret_access_key=minio_secret_key,
        region_name='us-east-1',
        config=boto3.session.Config(signature_version='s3v4'),
    )

    # List objects in the bucket
    response = s3.list_objects_v2(Bucket=bucket_name)
    current_files = set()
    if 'Contents' in response:
        for obj in response['Contents']:
            current_files.add(obj['Key'])

    # Get last seen files from XCom
    ti = kwargs['ti']
    last_files = ti.xcom_pull(task_ids='watch_minio_bucket', key='last_seen_files')
    if last_files is None:
        last_files = set()
    else:
        last_files = set(last_files)

    # Detect changes
    if current_files != last_files:
        # Update XCom with new file list
        ti.xcom_push(key='last_seen_files', value=list(current_files))
        print(f"Change detected in bucket {bucket_name}. New file list: {current_files}")
        return True
    print(f"No change detected in bucket {bucket_name}.")
    return False

# Example downstream task

def process_minio_changes(**kwargs):
    ti = kwargs['ti']
    file_list = ti.xcom_pull(task_ids='watch_minio_bucket', key='last_seen_files')
    print("Current files in MinIO bucket:")
    if file_list:
        for f in file_list:
            print(f" - {f}")
    else:
        print("(Bucket is empty)")

# Define the DAG

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2023, 1, 1),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'minio_file_watcher',
    default_args=default_args,
    description='Watches a MinIO bucket for file changes',
    schedule_interval='@once',  # or use a cron schedule as needed
    catchup=False,
    tags=['minio', 'file-watcher', 'sensor'],
)

watch_minio_bucket = PythonSensor(
    task_id='watch_minio_bucket',
    python_callable=minio_file_change_sensor,
    provide_context=True,
    poke_interval=30,  # Check every 30 seconds
    timeout=60 * 60,   # Timeout after 1 hour
    mode='poke',
    dag=dag,
)

process_changes = PythonOperator(
    task_id='process_minio_changes',
    python_callable=process_minio_changes,
    provide_context=True,
    dag=dag,
)

watch_minio_bucket >> process_changes 