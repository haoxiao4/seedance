import os

from anthropic import Anthropic

api_key = os.environ.get("ANTHROPIC_API_KEY")
if not api_key:
    raise ValueError("ANTHROPIC_API_KEY environment variable is not set")

client = Anthropic(
    # 推荐使用 127.0.0.1
    base_url="http://127.0.0.1:8045",
    api_key=api_key,
)

# 注意: Antigravity 支持使用 Anthropic SDK 调用任意模型
response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}]
)

print(response.content[0].text)