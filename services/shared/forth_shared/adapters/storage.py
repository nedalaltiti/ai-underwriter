# shared/forth_shared/adapters/storage.py
import os
from typing import Dict, Any, Optional
from pathlib import Path
import aioboto3
from loguru import logger


class S3Adapter:
    """AWS S3 storage adapter."""
    
    def __init__(
        self,
        bucket_name: str,
        region: str = "us-west-1",
        endpoint_url: Optional[str] = None
    ):
        self.bucket_name = bucket_name
        self.region = region
        self.endpoint_url = endpoint_url
        self._session = None
        
    async def _get_client(self):
        """Get S3 client."""
        if not self._session:
            self._session = aioboto3.Session(region_name=self.region)
        
        client_kwargs = {}
        if self.endpoint_url:
            client_kwargs["endpoint_url"] = self.endpoint_url
            
        return self._session.client("s3", **client_kwargs)
    
    async def upload_file(
        self,
        file_path: str,
        s3_key: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Upload file to S3."""
        try:
            async with await self._get_client() as s3:
                # Prepare metadata
                extra_args = {}
                if metadata:
                    extra_args["Metadata"] = {
                        k: str(v) for k, v in metadata.items()
                    }
                
                # Determine content type
                file_ext = Path(file_path).suffix.lower()
                content_type_map = {
                    ".pdf": "application/pdf",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".png": "image/png",
                    ".doc": "application/msword",
                    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                }
                content_type = content_type_map.get(file_ext, "application/octet-stream")
                extra_args["ContentType"] = content_type
                
                # Upload file
                await s3.upload_file(
                    Filename=file_path,
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    ExtraArgs=extra_args
                )
                
                # Generate S3 URL
                s3_url = f"s3://{self.bucket_name}/{s3_key}"
                
                logger.debug(f"📤 Uploaded to S3: {s3_key}")
                
                return {
                    "success": True,
                    "s3_key": s3_key,
                    "url": s3_url,
                    "content_type": content_type,
                    "bucket": self.bucket_name
                }
                
        except Exception as e:
            logger.error(f"❌ S3 upload failed: {e}")
            raise
    
    async def download_file(
        self,
        s3_key: str,
        local_path: str
    ) -> bool:
        """Download file from S3."""
        try:
            async with await self._get_client() as s3:
                await s3.download_file(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    Filename=local_path
                )
                logger.debug(f"📥 Downloaded from S3: {s3_key}")
                return True
                
        except Exception as e:
            logger.error(f"❌ S3 download failed: {e}")
            return False
    
    async def file_exists(self, s3_key: str) -> bool:
        """Check if file exists in S3."""
        try:
            async with await self._get_client() as s3:
                await s3.head_object(Bucket=self.bucket_name, Key=s3_key)
                return True
        except:
            return False
    
    async def delete_file(self, s3_key: str) -> bool:
        """Delete file from S3."""
        try:
            async with await self._get_client() as s3:
                await s3.delete_object(Bucket=self.bucket_name, Key=s3_key)
                logger.debug(f"🗑️ Deleted from S3: {s3_key}")
                return True
        except Exception as e:
            logger.error(f"❌ S3 delete failed: {e}")
            return False
    
    async def health_check(self) -> bool:
        """Check S3 connectivity."""
        try:
            async with await self._get_client() as s3:
                await s3.head_bucket(Bucket=self.bucket_name)
                return True
        except Exception as e:
            logger.error(f"❌ S3 health check failed: {e}")
            return False


class LocalStorageAdapter:
    """Local filesystem storage adapter for development."""
    
    def __init__(self, base_path: str = "/tmp/storage"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized local storage at: {self.base_path}")
    
    def _get_full_path(self, key: str) -> Path:
        """Get full filesystem path for a key."""
        return self.base_path / key
    
    async def upload_file(
        self,
        file_path: str,
        key: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Upload (copy) a file to local storage."""
        try:
            source = Path(file_path)
            dest = self._get_full_path(key)
            
            # Create parent directories
            dest.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy file
            import shutil
            shutil.copy2(source, dest)
            
            # Save metadata
            if metadata:
                metadata_path = dest.with_suffix(dest.suffix + '.metadata.json')
                import json
                with open(metadata_path, 'w') as f:
                    json.dump(metadata, f)
            
            file_size = dest.stat().st_size
            
            logger.info(f"Copied to local storage: {key}")
            
            return {
                "path": str(dest),
                "key": key,
                "url": f"file://{dest}",
                "file_size": file_size,
                "metadata": metadata
            }
            
        except Exception as e:
            logger.error(f"Local storage upload failed: {e}")
            raise
    
    async def download_file(self, key: str, local_path: str) -> str:
        """Download (copy) a file from local storage."""
        try:
            source = self._get_full_path(key)
            dest = Path(local_path)
            
            if not source.exists():
                raise FileNotFoundError(f"File not found: {key}")
            
            dest.parent.mkdir(parents=True, exist_ok=True)
            
            import shutil
            shutil.copy2(source, dest)
            
            logger.info(f"Copied from local storage: {key} -> {local_path}")
            return str(dest)
            
        except Exception as e:
            logger.error(f"Local storage download failed: {e}")
            raise
    
    async def delete_file(self, key: str) -> bool:
        """Delete a file from local storage."""
        try:
            file_path = self._get_full_path(key)
            if file_path.exists():
                file_path.unlink()
                
                # Also delete metadata if exists
                metadata_path = file_path.with_suffix(file_path.suffix + '.metadata.json')
                if metadata_path.exists():
                    metadata_path.unlink()
                
                logger.info(f"Deleted from local storage: {key}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Local storage delete failed: {e}")
            return False
    
    async def file_exists(self, key: str) -> bool:
        """Check if a file exists in local storage."""
        return self._get_full_path(key).exists()
    
    async def get_file_metadata(self, key: str) -> Optional[Dict[str, Any]]:
        """Get file metadata from local storage."""
        try:
            file_path = self._get_full_path(key)
            if not file_path.exists():
                return None
            
            stat = file_path.stat()
            
            # Load saved metadata
            metadata = {}
            metadata_path = file_path.with_suffix(file_path.suffix + '.metadata.json')
            if metadata_path.exists():
                import json
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
            
            return {
                "size": stat.st_size,
                "last_modified": datetime.fromtimestamp(stat.st_mtime),
                "metadata": metadata
            }
            
        except Exception as e:
            logger.error(f"Failed to get local storage metadata: {e}")
            return None
    
    async def health_check(self) -> bool:
        """Check local storage accessibility."""
        try:
            # Try to write and read a test file
            test_file = self.base_path / ".health_check"
            test_file.write_text("ok")
            result = test_file.read_text() == "ok"
            test_file.unlink()
            return result
        except Exception:
            return False
