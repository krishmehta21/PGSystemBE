import requests

# Test OCR.space API with free key
url = "https://api.ocr.space/parse/image"
payload = {
    "apikey": "donotusethiskey",
    "language": "eng",
    "isOverlayRequired": False
}

# Create a small dummy image of text to test
from PIL import Image, ImageDraw
img = Image.new('RGB', (300, 100), color = (255, 255, 255))
d = ImageDraw.Draw(img)
d.text((10,10), "Name: Krish Mehta\nDOB: 21/08/2000\nGender: Male\n1234 5678 9821", fill=(0,0,0))

import io
img_byte_arr = io.BytesIO()
img.save(img_byte_arr, format='PNG')
img_byte_arr = img_byte_arr.getvalue()

files = {
    "file": ("test.png", img_byte_arr, "image/png")
}

print("Sending request to OCR.space...")
try:
    response = requests.post(url, data=payload, files=files, timeout=15)
    result = response.json()
    print("Response Status:", response.status_code)
    print("Parsed Text Response:")
    if "ParsedResults" in result and len(result["ParsedResults"]) > 0:
        print(result["ParsedResults"][0]["ParsedText"])
    else:
        print("Error details:", result)
except Exception as e:
    print("Request failed:", e)
