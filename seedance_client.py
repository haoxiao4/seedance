"""
火山引擎 Seedance 视频生成 API 客户端

支持功能：
- 单图生视频（首帧图生视频）
- 首尾帧生视频
- 参考图生视频
- 有声视频生成（Seedance 1.5 pro）
"""

import os
import time
import requests
from typing import Optional, Literal, Dict, Any, Callable
from dataclasses import dataclass


@dataclass
class VideoTaskResult:
    """视频任务结果"""
    task_id: str
    status: str
    video_url: Optional[str] = None
    error_message: Optional[str] = None
    raw_response: Optional[Dict] = None


class SeedanceClient:
    """Seedance 视频生成 API 客户端"""

    # 任务状态
    STATUS_QUEUED = "queued"
    STATUS_RUNNING = "running"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"
    STATUS_EXPIRED = "expired"

    # 支持的模型
    MODEL_1_5_PRO = "doubao-seedance-1-5-pro-251215"
    MODEL_1_0_PRO = "doubao-seedance-1-0-pro-250528"
    MODEL_1_0_LITE = "doubao-seedance-1-0-lite-i2v"

    # 支持的分辨率
    RESOLUTIONS = ["480p", "720p", "1080p"]

    # 支持的宽高比
    RATIOS = ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9"]

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        """
        初始化客户端

        Args:
            api_key: API 密钥，默认从环境变量 ARK_API_KEY 读取
            base_url: API 基础 URL，默认从环境变量 ARK_BASE_URL 读取
        """
        self.api_key = api_key or os.getenv("ARK_API_KEY")
        self.base_url = base_url or os.getenv(
            "ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"
        )

        if not self.api_key:
            raise ValueError("API key is required. Set ARK_API_KEY environment variable or pass api_key parameter.")

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })

    def _build_content(
        self,
        mode: Literal["first_frame", "first_last_frame", "reference"],
        first_frame_url: Optional[str] = None,
        last_frame_url: Optional[str] = None,
        reference_url: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> list:
        """
        构建 content 数组

        Args:
            mode: 生成模式
            first_frame_url: 首帧图片 URL
            last_frame_url: 尾帧图片 URL
            reference_url: 参考图 URL
            prompt: 文本提示词
        """
        content = []

        if mode == "first_frame" and first_frame_url:
            content.append({
                "type": "image_url",
                "role": "first_frame",
                "image_url": {"url": first_frame_url}
            })

        elif mode == "first_last_frame":
            if first_frame_url:
                content.append({
                    "type": "image_url",
                    "role": "first_frame",
                    "image_url": {"url": first_frame_url}
                })
            if last_frame_url:
                content.append({
                    "type": "image_url",
                    "role": "last_frame",
                    "image_url": {"url": last_frame_url}
                })

        elif mode == "reference" and reference_url:
            content.append({
                "type": "image_url",
                "role": "reference",
                "image_url": {"url": reference_url}
            })

        if prompt:
            content.append({
                "type": "text",
                "text": prompt
            })

        return content

    def create_video_task(
        self,
        model: Optional[str] = None,
        mode: Literal["first_frame", "first_last_frame", "reference"] = "first_frame",
        first_frame_url: Optional[str] = None,
        last_frame_url: Optional[str] = None,
        reference_url: Optional[str] = None,
        prompt: Optional[str] = None,
        resolution: str = "720p",
        ratio: str = "16:9",
        duration: int = 5,
        generate_audio: bool = False,
        watermark: bool = False,
    ) -> VideoTaskResult:
        """
        创建视频生成任务

        Args:
            model: 模型 ID，默认从环境变量读取
            mode: 生成模式 - first_frame, first_last_frame, reference
            first_frame_url: 首帧图片 URL (支持 http/https 或 base64 data URI)
            last_frame_url: 尾帧图片 URL (仅首尾帧模式)
            reference_url: 参考图 URL (仅参考图模式)
            prompt: 文本提示词
            resolution: 分辨率 - 480p, 720p, 1080p
            ratio: 宽高比 - 16:9, 4:3, 1:1, 3:4, 9:16, 21:9
            duration: 视频时长(秒) - 2-12
            generate_audio: 是否生成音频 (仅 1.5 pro 支持)
            watermark: 是否添加水印

        Returns:
            VideoTaskResult: 任务结果对象
        """
        model = model or os.getenv("MODEL_ID", self.MODEL_1_5_PRO)

        # 参数验证
        if resolution not in self.RESOLUTIONS:
            raise ValueError(f"Invalid resolution: {resolution}. Must be one of {self.RESOLUTIONS}")
        if ratio not in self.RATIOS:
            raise ValueError(f"Invalid ratio: {ratio}. Must be one of {self.RATIOS}")
        if not 2 <= duration <= 12:
            raise ValueError(f"Invalid duration: {duration}. Must be between 2 and 12 seconds")

        # 构建 content
        content = self._build_content(mode, first_frame_url, last_frame_url, reference_url, prompt)

        if not content:
            raise ValueError("At least one image or text must be provided")

        # 构建请求体
        payload = {
            "model": model,
            "content": content,
            "resolution": resolution,
            "ratio": ratio,
            "duration": duration,
            "watermark": watermark,
        }

        # 仅当使用 1.5 pro 且需要生成音频时添加参数
        if generate_audio and "1-5-pro" in model:
            payload["generate_audio"] = True

        url = f"{self.base_url}/contents/generations/tasks"

        try:
            response = self.session.post(url, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()

            task_id = data.get("id")
            if not task_id:
                raise ValueError(f"No task ID in response: {data}")

            return VideoTaskResult(
                task_id=task_id,
                status=data.get("status", self.STATUS_QUEUED),
                raw_response=data
            )

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Failed to create video task: {e}") from e

    def query_task(self, task_id: str) -> VideoTaskResult:
        """
        查询任务状态

        Args:
            task_id: 任务 ID

        Returns:
            VideoTaskResult: 任务结果对象
        """
        url = f"{self.base_url}/contents/generations/tasks/{task_id}"

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            status = data.get("status", "unknown")
            video_url = None
            error_message = None

            if status == self.STATUS_SUCCEEDED:
                content = data.get("content", {})
                # content 可能是字典（如 {"video_url": "..."}）
                if isinstance(content, dict):
                    video_url = content.get("video_url")
                # content 也可能是数组（如 [{"type": "video_url", ...}])
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict):
                            if item.get("type") == "video_url":
                                video_url_data = item.get("video_url", {})
                                if isinstance(video_url_data, dict):
                                    video_url = video_url_data.get("url")
                                elif isinstance(video_url_data, str):
                                    video_url = video_url_data
                                break
                            # 处理直接包含 video_url 字段的情况
                            elif "video_url" in item:
                                video_url_data = item.get("video_url")
                                if isinstance(video_url_data, str):
                                    video_url = video_url_data
                                break
            elif status == self.STATUS_FAILED:
                error_data = data.get("error", {})
                if isinstance(error_data, dict):
                    error_message = error_data.get("message", "Unknown error")
                elif isinstance(error_data, str):
                    error_message = error_data
                else:
                    error_message = str(error_data)

            return VideoTaskResult(
                task_id=task_id,
                status=status,
                video_url=video_url,
                error_message=error_message,
                raw_response=data
            )

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Failed to query task: {e}") from e

    def wait_for_completion(
        self,
        task_id: str,
        poll_interval: int = 5,
        max_attempts: int = 60,
        callback: Optional[Callable] = None,
    ) -> VideoTaskResult:
        """
        轮询等待任务完成

        Args:
            task_id: 任务 ID
            poll_interval: 轮询间隔(秒)
            max_attempts: 最大轮询次数
            callback: 状态变更回调函数，接收 (status, result) 参数

        Returns:
            VideoTaskResult: 最终任务结果
        """
        last_status = None

        for attempt in range(max_attempts):
            result = self.query_task(task_id)

            # 状态变更时调用回调
            if callback and result.status != last_status:
                callback(result.status, result)
                last_status = result.status

            # 检查是否完成
            if result.status in (self.STATUS_SUCCEEDED, self.STATUS_FAILED, self.STATUS_EXPIRED):
                return result

            time.sleep(poll_interval)

        raise TimeoutError(f"Task {task_id} did not complete within {max_attempts * poll_interval} seconds")

    def download_video(
        self,
        video_url: str,
        output_path: str,
        chunk_size: int = 8192,
    ) -> str:
        """
        下载生成的视频

        Args:
            video_url: 视频 URL
            output_path: 保存路径
            chunk_size: 下载块大小

        Returns:
            str: 保存的文件路径
        """
        try:
            response = requests.get(video_url, stream=True, timeout=60)
            response.raise_for_status()

            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)

            return output_path

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Failed to download video: {e}") from e

    def create_single_image_video(
        self,
        image_url: str,
        prompt: Optional[str] = None,
        **kwargs
    ) -> VideoTaskResult:
        """
        单图生视频快捷方法

        Args:
            image_url: 图片 URL
            prompt: 文本提示词
            **kwargs: 其他参数传递给 create_video_task
        """
        return self.create_video_task(
            mode="first_frame",
            first_frame_url=image_url,
            prompt=prompt,
            **kwargs
        )

    def create_first_last_frame_video(
        self,
        first_frame_url: str,
        last_frame_url: str,
        prompt: Optional[str] = None,
        **kwargs
    ) -> VideoTaskResult:
        """
        首尾帧生视频快捷方法

        Args:
            first_frame_url: 首帧图片 URL
            last_frame_url: 尾帧图片 URL
            prompt: 文本提示词
            **kwargs: 其他参数传递给 create_video_task
        """
        return self.create_video_task(
            mode="first_last_frame",
            first_frame_url=first_frame_url,
            last_frame_url=last_frame_url,
            prompt=prompt,
            **kwargs
        )

    def create_audio_video(
        self,
        image_url: str,
        prompt: Optional[str] = None,
        **kwargs
    ) -> VideoTaskResult:
        """
        有声视频生成快捷方法 (仅 1.5 pro 支持)

        Args:
            image_url: 图片 URL
            prompt: 文本提示词
            **kwargs: 其他参数传递给 create_video_task
        """
        kwargs["generate_audio"] = True
        kwargs.setdefault("model", self.MODEL_1_5_PRO)
        return self.create_video_task(
            mode="first_frame",
            first_frame_url=image_url,
            prompt=prompt,
            **kwargs
        )
