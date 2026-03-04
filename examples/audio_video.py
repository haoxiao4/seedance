"""
有声视频生成示例
使用 Seedance 1.5 pro 模型生成带音频的视频
"""

import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from seedance_client import SeedanceClient


def main():
    # 加载环境变量
    load_dotenv()

    # 图片 URL
    image_url = input("请输入图片 URL: ").strip()
    if not image_url:
        print("错误：图片 URL 不能为空")
        return

    # 可选提示词（可以描述期望的音效）
    default_prompt = "cinematic shot with immersive sound, high quality audio"
    prompt = os.getenv("PROMPT", default_prompt)

    # 初始化客户端
    client = SeedanceClient()

    print(f"\n正在创建有声视频生成任务...")
    print(f"图片: {image_url[:80]}...")
    print(f"提示词: {prompt}")
    print(f"模型: {SeedanceClient.MODEL_1_5_PRO}")
    print(f"生成音频: 是")

    try:
        # 创建任务（有声视频模式）
        result = client.create_audio_video(
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
            print(f"\n✓ 有声视频生成成功!")

            # 调试输出：显示原始响应结构
            import json
            print(f"\n原始响应 (调试用):")
            print(json.dumps(final_result.raw_response, indent=2, ensure_ascii=False))

            if final_result.video_url:
                print(f"\n视频 URL: {final_result.video_url}")

                # 询问是否下载
                download = input("\n是否下载视频? (y/n): ").strip().lower()
                if download == "y":
                    output_path = input("请输入保存路径 (默认: audio_output.mp4): ").strip()
                    if not output_path:
                        output_path = "audio_output.mp4"

                    client.download_video(final_result.video_url, output_path)
                    print(f"视频已保存到: {output_path}")
            else:
                print(f"\n⚠ 任务成功但未找到视频 URL")
        else:
            print(f"\n✗ 任务失败: {final_result.error_message}")
            # 调试输出错误详情
            import json
            print(f"\n原始响应 (调试用):")
            print(json.dumps(final_result.raw_response, indent=2, ensure_ascii=False))

    except Exception as e:
        print(f"\n错误: {e}")


if __name__ == "__main__":
    main()
