import requests

# Test EasyOCR public API
url = "https://api.easyocr.org/ocr"

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

print("Sending request to EasyOCR public API...")
try:
    response = requests.post(url, files=files, timeout=15)
    print("Response Status:", response.status_code)
    print("Response JSON:", response.json())
except Exception as e:
    print("Request failed:", e)
