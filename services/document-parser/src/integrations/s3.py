# services/document-parser/src/integrations/s3.py
"""S3 integration for document retrieval."""

import tempfile
from typing import Dict, Any, Optional
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from config import config
from core.exceptions import DocumentDownloadError
from utils.logging import get_logger

logger = get_logger(__name__)


class S3Client:
    """Client for S3 operations."""
    
    def __init__(self):
        """Initialize S3 client."""
        try:
            session = boto3.Session(region_name=config.aws_region)
            
            if config.aws_endpoint_url:
                self.s3_client = session.client('s3', endpoint_url=config.aws_endpoint_url)
            else:
                self.s3_client = session.client('s3')
                
            self.bucket_name = config.s3_bucket_name
            logger.info(f"S3 client initialized for bucket: {self.bucket_name}")
            
        except NoCredentialsError:
            logger.error("AWS credentials not found")
            raise DocumentDownloadError("AWS credentials not configured")
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {e}")
            raise DocumentDownloadError(f"S3 client initialization failed: {e}")
    
    def download_document_from_s3(self, s3_key: str, bucket_override: Optional[str] = None) -> Dict[str, str]:
        """
        Download document from S3 and return base64 encoded data.
        
        Args:
            s3_key: S3 key of the document
            
        Returns:
            Dictionary with base64 encoded document data
        """
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                temp_path = Path(temp_file.name)
            
            # Download from S3
            bucket = bucket_override or self.bucket_name
            logger.info(f"Downloading document from S3: s3://{bucket}/{s3_key}")
            
            self.s3_client.download_file(
                Bucket=bucket,
                Key=s3_key,
                Filename=str(temp_path)
            )
            
            # Get file size
            file_size = temp_path.stat().st_size
            max_size = config.max_file_size_mb * 1024 * 1024
            
            if file_size > max_size:
                temp_path.unlink()  # Delete temp file
                raise DocumentDownloadError(
                    f"Document too large: {file_size} bytes (max: {max_size})"
                )
            
            # Read and encode file
            import base64
            with open(temp_path, 'rb') as f:
                content = f.read()
                content_encoded = base64.b64encode(content).decode("utf-8")
            
            # Clean up temp file
            temp_path.unlink()
            
            logger.info(f"Document downloaded from S3: {file_size} bytes")
            
            return {
                "mimeType": "application/pdf",
                "data": content_encoded
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                raise DocumentDownloadError(f"Document not found in S3: {s3_key}")
            elif error_code == 'NoSuchBucket':
                raise DocumentDownloadError(f"S3 bucket not found: {bucket}")
            else:
                raise DocumentDownloadError(f"S3 error ({error_code}): {e}")
        except Exception as e:
            raise DocumentDownloadError(f"Failed to download from S3: {e}")
    
    def get_presigned_url(self, s3_key: str, expiration: int = 3600) -> str:
        """
        Generate presigned URL for S3 object.
        
        Args:
            s3_key: S3 key of the document
            expiration: URL expiration time in seconds
            
        Returns:
            Presigned URL
        """
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': s3_key},
                ExpiresIn=expiration
            )
            return url
        except Exception as e:
            raise DocumentDownloadError(f"Failed to generate presigned URL: {e}")
    
    def check_document_exists(self, s3_key: str) -> bool:
        """
        Check if document exists in S3.
        
        Args:
            s3_key: S3 key to check
            
        Returns:
            True if document exists
        """
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            raise DocumentDownloadError(f"Error checking S3 object: {e}")
    
    def get_document_metadata(self, s3_key: str) -> Optional[Dict[str, Any]]:
        """
        Get document metadata from S3.
        
        Args:
            s3_key: S3 key of the document
            
        Returns:
            Document metadata or None if not found
        """
        try:
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return {
                'content_length': response.get('ContentLength'),
                'content_type': response.get('ContentType'),
                'last_modified': response.get('LastModified'),
                'metadata': response.get('Metadata', {})
            }
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return None
            raise DocumentDownloadError(f"Error getting S3 metadata: {e}")
        except Exception as e:
            raise DocumentDownloadError(f"Failed to get S3 metadata: {e}")