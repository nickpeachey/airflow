from airflow import DAG
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
from datetime import datetime, timedelta

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    dag_id='watch_s3_bucket',
    default_args=default_args,
    description='Watch for new files in an S3 bucket',
    schedule_interval='@hourly',
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['s3', 'sensor'],
) as dag:

    watch_for_file = S3KeySensor(
        task_id='watch_for_file',
        bucket_key='*',  # Watch for any file in the bucket
        bucket_name='data-lake',
        aws_conn_id='minio_conn',
        poke_interval=60,
        timeout=60 * 60,
        mode='poke',
    )