#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
腾讯云 COS 文件上传工具类
包含：文件上传、删除、SHA256去重、签名URL生成

环境变量配置（.env 文件）：
    COS_REGION=ap-guangzhou
    COS_BUCKET_NAME=your-bucket-name
    COS_ACCESS_KEY_ID=your-access-key-id
    COS_ACCESS_KEY_SECRET=your-access-key-secret
    COS_DOMAIN=https://cdn.example.com  # 可选，自定义CDN域名
    COS_USE_SIGNED_URL=true             # 可选，是否使用签名URL
    COS_SIGNED_URL_EXPIRE=3600          # 可选，签名URL过期时间（秒）
"""

import hashlib
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import unquote, urlparse

# 延迟导入，避免在没有安装SDK时出错
# pip install cos-python-sdk-v5


class COSConfig:
    """COS 配置类"""

    # 默认配置
    DEFAULT_REGION = "ap-guangzhou"
    DEFAULT_SIGNED_URL_EXPIRE = 3600

    @classmethod
    def from_env(cls) -> Dict[str, str]:
        """从环境变量读取配置"""
        config = {
            "region": os.getenv("COS_REGION", cls.DEFAULT_REGION),
            "bucket_name": os.getenv("COS_BUCKET_NAME", ""),
            "access_key_id": os.getenv("COS_ACCESS_KEY_ID", ""),
            "access_key_secret": os.getenv("COS_ACCESS_KEY_SECRET", ""),
            "session_token": os.getenv("COS_SESSION_TOKEN", ""),
            "domain": os.getenv("COS_DOMAIN", "").strip(),
            "use_signed_url": os.getenv("COS_USE_SIGNED_URL", "true").lower() in ("1", "true", "yes", "on"),
            "signed_url_expire": int(os.getenv("COS_SIGNED_URL_EXPIRE", str(cls.DEFAULT_SIGNED_URL_EXPIRE))),
        }

        # 验证必需配置
        required = ["bucket_name", "access_key_id", "access_key_secret"]
        missing = [k for k in required if not config.get(k)]
        if missing:
            raise ValueError(f"缺少必需的环境变量: {', '.join(missing)}")

        return config


class COSStorage:
    """腾讯云 COS 存储操作类"""

    # 默认图片处理规则（数据万象）
    DEFAULT_IMAGE_PROCESS_RULE = "imageMogr2/format/webp/quality/70"

    def __init__(self):
        self.config = COSConfig.from_env()
        self._client = None
        self._bucket_name = None

    def _get_client(self) -> Tuple[Any, str]:
        """获取 COS 客户端和 bucket 名称（延迟初始化）"""
        if self._client is None:
            from qcloud_cos import CosConfig, CosS3Client

            config_kwargs: Dict[str, Any] = {
                "Region": self.config["region"],
                "SecretId": self.config["access_key_id"],
                "SecretKey": self.config["access_key_secret"],
                "Scheme": "https",
            }
            if self.config.get("session_token"):
                config_kwargs["Token"] = self.config["session_token"]

            cos_config = CosConfig(**config_kwargs)
            self._client = CosS3Client(cos_config)
            self._bucket_name = self.config["bucket_name"]

        return self._client, self._bucket_name

    def get_domain(self) -> str:
        """获取访问域名"""
        custom_domain = self.config.get("domain", "")
        if custom_domain:
            if custom_domain.startswith(("http://", "https://")):
                return custom_domain.rstrip("/")
            return f"https://{custom_domain.rstrip('/')}"

        return f"https://{self.config['bucket_name']}.cos.{self.config['region']}.myqcloud.com"

    def build_key(self, folder: str, filename: str) -> str:
        """构建存储路径"""
        return f"{folder}/{filename}".lstrip("/")

    def build_url(self, key: str) -> str:
        """构建访问 URL"""
        return f"{self.get_domain()}/{key.lstrip('/')}"

    # ==================== 核心上传方法 ====================

    def upload_bytes(
        self,
        key: str,
        content: bytes,
        content_type: Optional[str] = None,
    ) -> str:
        """
        上传字节流到 COS

        Args:
            key: 存储路径，如 "products/image.jpg"
            content: 文件字节内容
            content_type: MIME类型，如 "image/jpeg"

        Returns:
            文件的访问 URL
        """
        client, bucket_name = self._get_client()

        put_kwargs: Dict[str, Any] = {
            "Bucket": bucket_name,
            "Body": content,
            "Key": key.lstrip("/"),
        }
        if content_type:
            put_kwargs["ContentType"] = content_type

        client.put_object(**put_kwargs)
        return self.build_url(key)

    def upload_file(
        self,
        file_path: Union[str, Path],
        key: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> str:
        """
        上传本地文件到 COS

        Args:
            file_path: 本地文件路径
            key: 存储路径，不传则使用文件名
            content_type: MIME类型

        Returns:
            文件的访问 URL
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        if key is None:
            key = file_path.name

        content = file_path.read_bytes()
        return self.upload_bytes(key, content, content_type)

    def upload_with_auto_key(
        self,
        filename: str,
        content: bytes,
        folder: str = "products",
        content_type: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        上传文件并自动生成唯一文件名

        Args:
            filename: 原始文件名
            content: 文件字节内容
            folder: 存储目录
            content_type: MIME类型

        Returns:
            包含 url, path, filename 的字典
        """
        # 生成唯一文件名: 时间戳_随机8位.扩展名
        ext = Path(filename).suffix.lower()
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        new_filename = f"{timestamp}_{unique_id}{ext}"

        key = self.build_key(folder, new_filename)
        url = self.upload_bytes(key, content, content_type)

        return {
            "url": url,
            "path": key,
            "filename": new_filename,
            "original_filename": filename,
        }

    # ==================== 删除操作 ====================

    def delete(self, key: str) -> None:
        """删除 COS 上的文件"""
        client, bucket_name = self._get_client()
        client.delete_object(Bucket=bucket_name, Key=key.lstrip("/"))

    def delete_by_url(self, url: str) -> None:
        """通过 URL 删除文件"""
        key = self.parse_key_from_url(url)
        if key:
            self.delete(key)

    # ==================== 查询操作 ====================

    def exists(self, key: str) -> bool:
        """检查文件是否存在"""
        from qcloud_cos.cos_exception import CosServiceError

        client, bucket_name = self._get_client()
        try:
            client.head_object(Bucket=bucket_name, Key=key.lstrip("/"))
            return True
        except CosServiceError as exc:
            status_code = getattr(exc, "status_code", None)
            if status_code == 404:
                return False
            # 兼容某些版本 SDK
            get_status_code = getattr(exc, "get_status_code", None)
            if callable(get_status_code) and get_status_code() == 404:
                return False
            raise

    # ==================== 签名 URL ====================

    def get_presigned_url(self, key: str, expire: Optional[int] = None) -> str:
        """
        获取带签名的临时访问链接

        Args:
            key: 存储路径
            expire: 过期时间（秒），默认使用配置

        Returns:
            签名后的临时 URL
        """
        client, bucket_name = self._get_client()
        ttl = expire if expire is not None else self.config["signed_url_expire"]
        ttl = max(60, ttl)  # 最小60秒

        return client.get_presigned_download_url(
            Bucket=bucket_name,
            Key=key.lstrip("/"),
            Expired=ttl,
        )

    def maybe_sign_url(self, url: str) -> str:
        """如果配置为使用签名URL，则添加签名"""
        if not self.config["use_signed_url"]:
            return url

        key = self.parse_key_from_url(url)
        if not key:
            return url

        try:
            return self.get_presigned_url(key)
        except Exception:
            return url

    # ==================== URL 处理 ====================

    def parse_key_from_url(self, url: str) -> Optional[str]:
        """从 COS URL 中提取对象 key"""
        if not self._is_remote_url(url):
            return None

        parsed = urlparse(url)
        domain = self.get_domain().replace("https://", "").replace("http://", "")

        if domain not in parsed.netloc:
            return None

        path = unquote(parsed.path or "")
        key = path.lstrip("/")
        return key or None

    @staticmethod
    def _is_remote_url(url: str) -> bool:
        """判断是否为远程 URL"""
        return url.startswith(("http://", "https://"))

    # ==================== 图片处理 ====================

    def append_image_process(self, url: str, rule: Optional[str] = None) -> str:
        """
        在 URL 后追加图片处理参数（数据万象）

        Args:
            url: 原始图片 URL
            rule: 处理规则，默认使用 webp 压缩 quality/70

        Returns:
            添加处理参数后的 URL
        """
        if rule is None:
            rule = self.DEFAULT_IMAGE_PROCESS_RULE

        key = self.parse_key_from_url(url)
        if not key:
            return url

        parsed = urlparse(url)
        query = parsed.query or ""

        # 避免重复添加
        if "imagemogr2/" in query.lower():
            return url

        delimiter = "&" if query else "?"
        return f"{url}{delimiter}{rule.lstrip('?&')}"

    def get_optimized_image_url(self, url: str) -> str:
        """获取优化后的图片 URL（签名+压缩）"""
        signed_url = self.maybe_sign_url(url)
        return self.append_image_process(signed_url)


# ==================== SHA256 去重工具 ====================

class FileHashUtil:
    """文件哈希工具类（用于实现秒传功能）"""

    @staticmethod
    def calculate_hash(content: bytes) -> str:
        """计算文件的 SHA256 哈希值"""
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def calculate_hash_from_file(file_path: Union[str, Path]) -> str:
        """计算本地文件的 SHA256 哈希值"""
        content = Path(file_path).read_bytes()
        return FileHashUtil.calculate_hash(content)


class COSUploaderWithDeduplication(COSStorage):
    """
    带去重功能的上传器
    需要配合数据库使用，示例中使用内存字典模拟
    """

    def __init__(self):
        super().__init__()
        # 实际项目中应该使用数据库，这里用内存字典演示
        self._hash_store: Dict[str, Dict] = {}

    def upload_with_dedup(
        self,
        filename: str,
        content: bytes,
        folder: str = "products",
        content_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        上传文件，自动去重

        Returns:
            {
                "url": "文件URL",
                "path": "存储路径",
                "filename": "新文件名",
                "file_hash": "SHA256哈希",
                "duplicate": False,  # 是否为重复文件
            }
        """
        # 计算文件哈希
        file_hash = FileHashUtil.calculate_hash(content)

        # 检查是否已存在
        existing = self._hash_store.get(file_hash)
        if existing:
            print(f"[秒传] 文件已存在: {existing['original_filename']}")
            return {
                "url": existing["oss_url"],
                "path": existing["oss_path"],
                "filename": existing["original_filename"],
                "file_hash": file_hash,
                "duplicate": True,
            }

        # 新文件，执行上传
        result = self.upload_with_auto_key(
            filename=filename,
            content=content,
            folder=folder,
            content_type=content_type,
        )

        # 保存哈希记录
        self._hash_store[file_hash] = {
            "file_hash": file_hash,
            "original_filename": filename,
            "oss_path": result["path"],
            "oss_url": result["url"],
            "file_size": len(content),
            "mime_type": content_type,
        }

        return {
            **result,
            "file_hash": file_hash,
            "duplicate": False,
        }


# ==================== 使用示例 ====================

def demo():
    """演示如何使用 COS 上传工具"""

    # 1. 基础上传
    cos = COSStorage()

    # 上传字节流
    # url = cos.upload_bytes("test/hello.txt", b"Hello COS!")
    # print(f"上传成功: {url}")

    # 上传本地文件
    # url = cos.upload_file("/path/to/image.jpg", folder="products")
    # print(f"上传成功: {url}")

    # 2. 自动生成文件名上传
    # result = cos.upload_with_auto_key(
    #     filename="image.jpg",
    #     content=b"...image bytes...",
    #     folder="products/good_images",
    #     content_type="image/jpeg"
    # )
    # print(result)
    # 输出: {'url': 'https://...', 'path': 'products/...', 'filename': '...'}

    # 3. 获取签名URL（私有文件访问）
    # signed_url = cos.get_presigned_url("products/image.jpg", expire=3600)
    # print(f"签名URL: {signed_url}")

    # 4. 图片处理URL
    # optimized_url = cos.get_optimized_image_url("https://.../image.jpg")
    # print(f"优化后URL: {optimized_url}")

    # 5. 带去重的上传
    # uploader = COSUploaderWithDeduplication()
    # result = uploader.upload_with_dedup("file.jpg", b"...content...")
    # if result["duplicate"]:
    #     print("秒传成功！")

    print("演示完成，请取消注释实际代码后使用")


if __name__ == "__main__":
    demo()
