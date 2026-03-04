"""
首尾帧生视频示例
传入首帧和尾帧两张图片，生成从首帧过渡到尾帧的视频
"""

import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from seedance_client import SeedanceClient


def main():
    # 加载环境变量
    load_dotenv()

    # 获取图片 URL
    first_frame_url = input("请输入首帧图片 URL: ").strip()
    if not first_frame_url:
        print("错误：首帧图片 URL 不能为空")
        return

    last_frame_url = input("请输入尾帧图片 URL: ").strip()
    if not last_frame_url:
        print("错误：尾帧图片 URL 不能为空")
        return

    # 可选提示词
    prompt = os.getenv("PROMPT", "smooth transition, cinematic quality")

    # 初始化客户端
    client = SeedanceClient()

    print(f"\n正在创建首尾帧视频生成任务...")
    print(f"首帧: {first_frame_url[:60]}...")
    print(f"尾帧: {last_frame_url[:60]}...")
    print(f"提示词: {prompt}")

    try:
        # 创建任务（首尾帧模式）
        result = client.create_first_last_frame_video(
            first_frame_url=first_frame_url,
            last_frame_url=last_frame_url,
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
