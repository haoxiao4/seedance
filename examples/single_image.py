"""
单图生视频示例
传入一张图片，生成以该图片为首帧的视频
"""

import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from seedance_client import SeedanceClient


def main():
    # 加载环境变量
    load_dotenv()

    # 图片 URL（可以是 http/https 链接或 base64 data URI）
    # 示例：使用在线图片
    image_url = input("请输入图片 URL: ").strip()

    if not image_url:
        print("错误：图片 URL 不能为空")
        return

    # 可选提示词
    prompt = os.getenv("PROMPT", "cinematic shot, high quality, smooth motion")

    # 初始化客户端
    client = SeedanceClient()

    print(f"\n正在创建视频生成任务...")
    print(f"图片: {image_url[:80]}...")
    print(f"提示词: {prompt}")

    try:
        # 创建任务
        result = client.create_single_image_video(
            image_url=image_url,
            prompt=prompt,
            resolution=os.getenv("RESOLUTION", "720p"),
            ratio=os.getenv("RATIO", "16:9"),
            duration=int(os.getenv("DURATION", "5")),
            watermark=os.getenv("WATERMARK", "false").lower() == "true",
        )

        print(f"任务创建成功: {result.task_id}")
        print(f"初始状态: {result.status}")

        # 定义状态回调
        def on_status_change(status, result):
            print(f"  → 状态更新: {status}")

        # 等待完成
        print(f"\n等待任务完成...")
        final_result = client.wait_for_completion(
            result.task_id,
            poll_interval=5,
            callback=on_status_change,
        )

        # 处理结果
        if final_result.status == client.STATUS_SUCCEEDED:
            print(f"\n✓ 视频生成成功!")
            print(f"视频 URL: {final_result.video_url}")

            # 询问是否下载
            download = input("\n是否下载视频? (y/n): ").strip().lower()
            if download == "y":
                output_path = input("请输入保存路径 (默认: output.mp4): ").strip()
                if not output_path:
                    output_path = "output.mp4"

                client.download_video(final_result.video_url, output_path)
                print(f"视频已保存到: {output_path}")
        else:
            print(f"\n✗ 任务失败: {final_result.error_message}")

    except Exception as e:
        print(f"\n错误: {e}")


if __name__ == "__main__":
    main()
