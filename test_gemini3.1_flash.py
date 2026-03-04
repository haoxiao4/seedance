from anthropic import Anthropic

client = Anthropic(
    # 推荐使用 127.0.0.1
    base_url="http://127.0.0.1:8045",
    api_key="sk-a4942499198e45c5bd42d55a9600d624"
)

# 注意: Antigravity 支持使用 Anthropic SDK 调用任意模型
response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}]
)

print(response.content[0].text)