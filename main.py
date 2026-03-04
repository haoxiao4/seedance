#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Seedance 图生视频 Web 应用 - 极简版
单文件 FastAPI 后端，包含：API + 任务处理 + COS 上传
"""

import os
import json
import uuid
import hashlib
import threading
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from dataclasses import dataclass, asdict

import requests
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# 从现有文件导入
from seedance_client import SeedanceClient, VideoTaskResult

# ==================== 配置 ====================

# 密码保护（从环境变量读取，默认简单密码）
ACCESS_PASSWORD = os.getenv("ACCESS_PASSWORD", "seedance2024")

# COS 配置
COS_REGION = os.getenv("COS_REGION", "ap-guangzhou")
COS_BUCKET_NAME = os.getenv("COS_BUCKET_NAME", "")
COS_ACCESS_KEY_ID = os.getenv("COS_ACCESS_KEY_ID", "")
COS_ACCESS_KEY_SECRET = os.getenv("COS_ACCESS_KEY_SECRET", "")
COS_DOMAIN = os.getenv("COS_DOMAIN", "").strip()

# Seedance API 配置
ARK_API_KEY = os.getenv("ARK_API_KEY")
ARK_BASE_URL = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")

# 数据库路径
DB_PATH = os.getenv("DB_PATH", "tasks.db")

# ==================== 数据库 ====================

@contextmanager
def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """初始化数据库表"""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'pending',
                mode TEXT NOT NULL,
                prompt TEXT,
                resolution TEXT,
                ratio TEXT,
                duration INTEGER,
                generate_audio BOOLEAN,
                watermark BOOLEAN,
                image_urls TEXT,
                video_url TEXT,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


# ==================== COS 工具 ====================

class COSStorage:
    """简化的 COS 存储类"""

    def __init__(self):
        self.config = {
            "region": COS_REGION,
            "bucket_name": COS_BUCKET_NAME,
            "access_key_id": COS_ACCESS_KEY_ID,
            "access_key_secret": COS_ACCESS_KEY_SECRET,
            "domain": COS_DOMAIN,
        }
        self._client = None

    def _get_client(self):
        if self._client is None:
            from qcloud_cos import CosConfig, CosS3Client
            cos_config = CosConfig(
                Region=self.config["region"],
                SecretId=self.config["access_key_id"],
                SecretKey=self.config["access_key_secret"],
                Scheme="https",
            )
            self._client = CosS3Client(cos_config)
        return self._client

    def get_domain(self) -> str:
        if self.config["domain"]:
            domain = self.config["domain"].rstrip("/")
            if not domain.startswith(("http://", "https://")):
                domain = f"https://{domain}"
            return domain
        return f"https://{self.config['bucket_name']}.cos.{self.config['region']}.myqcloud.com"

    def upload_bytes(self, key: str, content: bytes, content_type: Optional[str] = None) -> str:
        client = self._get_client()
        kwargs = {
            "Bucket": self.config["bucket_name"],
            "Body": content,
            "Key": key.lstrip("/"),
        }
        if content_type:
            kwargs["ContentType"] = content_type
        client.put_object(**kwargs)
        return f"{self.get_domain()}/{key.lstrip('/')}"

    def upload_with_auto_key(self, filename: str, content: bytes, folder: str = "seedance") -> Dict[str, str]:
        ext = Path(filename).suffix.lower() or ".bin"
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        new_filename = f"{timestamp}_{unique_id}{ext}"
        key = f"{folder}/{new_filename}"
        url = self.upload_bytes(key, content, self._guess_content_type(ext))
        return {"url": url, "path": key, "filename": new_filename}

    @staticmethod
    def _guess_content_type(ext: str) -> Optional[str]:
        mapping = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".gif": "image/gif",
            ".webp": "image/webp", ".mp4": "video/mp4",
            ".mov": "video/quicktime", ".webm": "video/webm",
        }
        return mapping.get(ext.lower())


cos_storage: Optional[COSStorage] = None

def get_cos() -> COSStorage:
    global cos_storage
    if cos_storage is None:
        cos_storage = COSStorage()
    return cos_storage


# ==================== 数据模型 ====================

@dataclass
class Task:
    id: str
    status: str  # pending, processing, completed, failed
    mode: str  # first_frame, first_last_frame, reference
    prompt: str
    resolution: str
    ratio: str
    duration: int
    generate_audio: bool
    watermark: bool
    image_urls: List[str]
    video_url: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            **asdict(self),
            "image_urls": json.dumps(self.image_urls) if isinstance(self.image_urls, list) else self.image_urls,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Task":
        data = dict(row)
        image_urls = data.get("image_urls", "[]")
        if isinstance(image_urls, str):
            try:
                image_urls = json.loads(image_urls)
            except:
                image_urls = []
        return cls(
            id=data["id"],
            status=data["status"],
            mode=data["mode"],
            prompt=data.get("prompt", ""),
            resolution=data.get("resolution", "720p"),
            ratio=data.get("ratio", "16:9"),
            duration=data.get("duration", 5),
            generate_audio=bool(data.get("generate_audio", False)),
            watermark=bool(data.get("watermark", False)),
            image_urls=image_urls,
            video_url=data.get("video_url"),
            error_message=data.get("error_message"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


# ==================== 任务处理 ====================

def process_task(task_id: str):
    """后台线程处理任务"""
    try:
        with get_db() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                return
            task = Task.from_row(row)

        # 更新状态为处理中
        _update_task_status(task_id, "processing")

        # 初始化客户端
        client = SeedanceClient(api_key=ARK_API_KEY, base_url=ARK_BASE_URL)

        # 根据模式获取图片URL
        image_urls = task.image_urls if isinstance(task.image_urls, list) else json.loads(task.image_urls or "[]")

        # 调用 API 创建任务
        result = client.create_video_task(
            mode=task.mode,  # type: ignore
            first_frame_url=image_urls[0] if len(image_urls) > 0 else None,
            last_frame_url=image_urls[1] if len(image_urls) > 1 and task.mode == "first_last_frame" else None,
            reference_url=image_urls[0] if task.mode == "reference" else None,
            prompt=task.prompt if task.prompt else None,
            resolution=task.resolution,
            ratio=task.ratio,
            duration=task.duration,
            generate_audio=task.generate_audio,
            watermark=task.watermark,
        )

        # 轮询等待完成
        final_result = client.wait_for_completion(
            result.task_id,
            poll_interval=5,
            max_attempts=120,  # 最多10分钟
        )

        if final_result.status == "succeeded" and final_result.video_url:
            # 下载视频
            video_content = requests.get(final_result.video_url, timeout=60).content
            # 上传到 COS
            cos = get_cos()
            upload_result = cos.upload_with_auto_key("video.mp4", video_content, folder="seedance/videos")
            # 更新任务
            _update_task_status(task_id, "completed", video_url=upload_result["url"])
        else:
            _update_task_status(
                task_id, "failed",
                error_message=final_result.error_message or "Video generation failed"
            )

    except Exception as e:
        _update_task_status(task_id, "failed", error_message=str(e))


def _update_task_status(task_id: str, status: str, video_url: Optional[str] = None, error_message: Optional[str] = None):
    """更新任务状态"""
    with get_db() as conn:
        updates = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
        params: List[Any] = [status]

        if video_url:
            updates.append("video_url = ?")
            params.append(video_url)
        if error_message:
            updates.append("error_message = ?")
            params.append(error_message)

        params.append(task_id)
        conn.execute(
            f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?",
            params
        )


# ==================== FastAPI 应用 ====================

app = FastAPI(title="Seedance Web", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 密码验证
def verify_password(password: str = Form(...)):
    if password != ACCESS_PASSWORD:
        raise HTTPException(status_code=403, detail="Invalid password")
    return True


# ==================== API 路由 ====================

@app.on_event("startup")
async def startup():
    init_db()


@app.get("/", response_class=HTMLResponse)
async def index():
    """返回前端页面"""
    return FileResponse("index.html")


@app.post("/api/upload")
async def upload_image(
    file: UploadFile = File(...),
    password: str = Form(...),
) -> Dict[str, str]:
    """上传图片到 COS"""
    verify_password(password)

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB 限制
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    cos = get_cos()
    result = cos.upload_with_auto_key(file.filename or "image.jpg", content, folder="seedance/images")

    return {"url": result["url"], "filename": result["filename"]}


@app.post("/api/tasks")
async def create_task(
    mode: str = Form(...),
    image_urls: str = Form(...),  # JSON array string
    prompt: str = Form(""),
    resolution: str = Form("480p"),
    ratio: str = Form("16:9"),
    duration: int = Form(5),
    generate_audio: bool = Form(False),
    watermark: bool = Form(False),
    password: str = Form(...),
) -> Dict[str, Any]:
    """创建视频生成任务"""
    verify_password(password)

    task_id = uuid.uuid4().hex[:16]

    # 解析图片URL
    urls = json.loads(image_urls)
    if not urls or not isinstance(urls, list):
        raise HTTPException(status_code=400, detail="At least one image required")

    # 保存任务
    task = Task(
        id=task_id,
        status="pending",
        mode=mode,
        prompt=prompt,
        resolution=resolution,
        ratio=ratio,
        duration=duration,
        generate_audio=generate_audio,
        watermark=watermark,
        image_urls=urls,
    )

    with get_db() as conn:
        conn.execute(
            """INSERT INTO tasks (id, status, mode, prompt, resolution, ratio, duration,
                generate_audio, watermark, image_urls)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task.id, task.status, task.mode, task.prompt, task.resolution,
             task.ratio, task.duration, task.generate_audio, task.watermark,
             json.dumps(task.image_urls))
        )

    # 启动后台线程处理
    threading.Thread(target=process_task, args=(task_id,), daemon=True).start()

    return {"task_id": task_id, "status": "pending"}


@app.get("/api/tasks")
async def list_tasks(
    password: str,
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """获取任务列表"""
    verify_password(password)

    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]

    tasks = [Task.from_row(row).__dict__ for row in rows]
    return {"tasks": tasks, "total": total}


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str, password: str) -> Dict[str, Any]:
    """获取单个任务详情"""
    verify_password(password)

    with get_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Task not found")

    return Task.from_row(row).__dict__


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str, password: str) -> Dict[str, str]:
    """删除任务"""
    verify_password(password)

    with get_db() as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

    return {"message": "Task deleted"}


# ==================== 静态文件 ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
