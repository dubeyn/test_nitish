
import requests, base64, json

invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"
stream = True

image_url = "https://m.media-amazon.com/images/I/51sG+agaZbS._SL1280_.jpg"  # URL to your JPG file
image_b64 = base64.b64encode(requests.get(image_url).content).decode("utf-8")


headers = {
  "Authorization": "Bearer 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",
  "Accept": "text/event-stream" if stream else "application/json"
}

payload = {
  "model": "google/gemma-3n-e4b-it",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "is there a moon?"
        },
        {
          "type": "image_url",
          "image_url": {
            "url": f"data:image/jpeg;base64,{image_b64}"
          }
        }
      ]
    }
  ],
  "max_tokens": 512,
  "temperature": 0.20,
  "top_p": 0.70,
  "frequency_penalty": 0.00,
  "presence_penalty": 0.00,
  "stream": stream
}

response = requests.post(invoke_url, headers=headers, json=payload)

if stream:
    for line in response.iter_lines():
        if line:
            text = line.decode("utf-8")
            if text.startswith("data: "):
                text = text[len("data: "):]
            if text == "[DONE]":
                break
            try:
                chunk = json.loads(text)
                content = chunk["choices"][0]["delta"].get("content", "")
                if content:
                    print(content, end="", flush=True)
            except json.JSONDecodeError:
                pass
    print()  # newline at end
else:
    print(response.json())
