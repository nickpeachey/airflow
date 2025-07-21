import os
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.datasets import Dataset
from airflow.utils.dates import days_ago

# Define datasets - these will be visible in the Airflow UI
raw_data_dataset = Dataset("s3://my-minio-bucket/raw-data/")
processed_data_dataset = Dataset("s3://my-minio-bucket/processed-data/")
analytics_dataset = Dataset("s3://my-minio-bucket/analytics/")

def extract_data():
    """Simulate data extraction"""
    print("Extracting raw data from source...")
    print("Data extracted successfully!")
    return "raw_data.csv"

def process_data():
    """Simulate data processing"""
    print("Processing raw data...")
    print("Data processed successfully!")
    return "processed_data.csv"

def run_analytics():
    """Simulate analytics computation"""
    print("Running analytics on processed data...")
    print("Analytics completed successfully!")
    return "analytics_report.json"

# DAG 1: Data Pipeline Producer
producer_dag = DAG(
    'dataset_producer_pipeline',
    default_args={
        'start_date': days_ago(1),
        'retries': 1,
    },
    description='A data pipeline that produces datasets',
    schedule_interval=timedelta(hours=6),  # Runs every 6 hours
    catchup=False,
    tags=['datasets', 'data-pipeline', 'producer'],
)

# Task that produces raw data dataset
extract_task = PythonOperator(
    task_id='extract_raw_data',
    python_callable=extract_data,
    outlets=[raw_data_dataset],  # This task produces the raw_data_dataset
    dag=producer_dag,
)

# Task that consumes raw data and produces processed data
process_task = PythonOperator(
    task_id='process_data',
    python_callable=process_data,
    inlets=[raw_data_dataset],      # This task consumes raw_data_dataset
    outlets=[processed_data_dataset],  # This task produces processed_data_dataset
    dag=producer_dag,
)

# Task that consumes processed data and produces analytics
analytics_task = PythonOperator(
    task_id='run_analytics',
    python_callable=run_analytics,
    inlets=[processed_data_dataset],   # This task consumes processed_data_dataset
    outlets=[analytics_dataset],       # This task produces analytics_dataset
    dag=producer_dag,
)

# Set task dependencies
extract_task >> process_task >> analytics_task

# DAG 2: Dataset Consumer (triggered by dataset updates)
consumer_dag = DAG(
    'dataset_consumer_pipeline',
    default_args={
        'start_date': days_ago(1),
        'retries': 1,
    },
    description='A pipeline that is triggered by dataset updates',
    schedule=[analytics_dataset],  # This DAG is triggered when analytics_dataset is updated
    catchup=False,
    tags=['datasets', 'consumer', 'triggered'],
)

def send_notification():
    """Send notification about new analytics data"""
    print("New analytics data is available!")
    print("Sending notification to stakeholders...")
    return "notification_sent"

def generate_report():
    """Generate a report based on analytics data"""
    print("Generating executive report...")
    print("Report generated successfully!")
    return "executive_report.pdf"

# Tasks in the consumer DAG
notification_task = PythonOperator(
    task_id='send_notification',
    python_callable=send_notification,
    inlets=[analytics_dataset],  # This task consumes the analytics_dataset
    dag=consumer_dag,
)

report_task = PythonOperator(
    task_id='generate_report',
    python_callable=generate_report,
    inlets=[analytics_dataset],  # This task also consumes the analytics_dataset
    dag=consumer_dag,
)

# Consumer tasks can run in parallel
notification_task
report_task

# DAG 3: Manual Dataset Trigger Example
manual_dag = DAG(
    'manual_dataset_trigger',
    default_args={
        'start_date': days_ago(1),
    },
    description='Manually trigger dataset updates for testing',
    schedule_interval=None,  # Manual trigger only
    catchup=False,
    tags=['datasets', 'manual', 'testing'],
)

def trigger_dataset_update():
    """Simulate a manual dataset update"""
    print("Manually updating dataset...")
    print("Dataset updated successfully!")

manual_trigger_task = PythonOperator(
    task_id='manual_dataset_update',
    python_callable=trigger_dataset_update,
    outlets=[raw_data_dataset],  # This will trigger any DAG scheduled on this dataset
    dag=manual_dag,
)

# DAG 4: Multiple Dataset Dependencies
multi_dataset_dag = DAG(
    'multiple_dataset_consumer',
    default_args={
        'start_date': days_ago(1),
    },
    description='DAG that waits for multiple datasets',
    schedule=[raw_data_dataset, processed_data_dataset],  # Triggered when BOTH datasets are updated
    catchup=False,
    tags=['datasets', 'multiple-dependencies'],
)

def process_multiple_datasets():
    """Process data from multiple datasets"""
    print("Processing data from multiple datasets...")
    print("Cross-dataset analysis completed!")

multi_dataset_task = PythonOperator(
    task_id='process_multiple_datasets',
    python_callable=process_multiple_datasets,
    inlets=[raw_data_dataset, processed_data_dataset],  # Consumes both datasets
    dag=multi_dataset_dag,
)
