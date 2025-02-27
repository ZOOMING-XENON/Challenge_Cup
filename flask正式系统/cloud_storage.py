import oss2
from qcloud_cos import CosConfig, CosS3Client
import boto3
from cloud_config import CLOUD_STORAGE_CONFIG

class CloudStorage:
    @staticmethod
    def upload_to_cloud(file_path, cloud_path, provider):
        if provider == 'aliyun':
            return CloudStorage.upload_to_aliyun(file_path, cloud_path)
        elif provider == 'qcloud':
            return CloudStorage.upload_to_qcloud(file_path, cloud_path)
        elif provider == 'aws':
            return CloudStorage.upload_to_aws(file_path, cloud_path)
        else:
            raise ValueError(f"不支持的云存储提供商: {provider}")

    @staticmethod
    def upload_to_aliyun(file_path, cloud_path):
        config = CLOUD_STORAGE_CONFIG['aliyun']
        auth = oss2.Auth(config['access_key_id'], config['access_key_secret'])
        bucket = oss2.Bucket(auth, config['endpoint'], config['bucket_name'])
        
        with open(file_path, 'rb') as f:
            bucket.put_object(cloud_path, f)
        return True

    @staticmethod
    def upload_to_qcloud(file_path, cloud_path):
        config = CLOUD_STORAGE_CONFIG['qcloud']
        cos_config = CosConfig(
            Region=config['region'],
            SecretId=config['secret_id'],
            SecretKey=config['secret_key']
        )
        client = CosS3Client(cos_config)
        
        response = client.upload_file(
            Bucket=config['bucket_name'],
            LocalFilePath=file_path,
            Key=cloud_path
        )
        return True

    @staticmethod
    def upload_to_aws(file_path, cloud_path):
        config = CLOUD_STORAGE_CONFIG['aws']
        s3_client = boto3.client('s3',
            aws_access_key_id=config['aws_access_key_id'],
            aws_secret_access_key=config['aws_secret_access_key'],
            region_name=config['region_name']
        )
        
        s3_client.upload_file(file_path, config['bucket_name'], cloud_path)
        return True 