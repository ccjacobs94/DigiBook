import pytesseract
from PIL import Image

image = Image.open('static/logo.png')
text = pytesseract.image_to_string(image)
print("EXTRACTED TEXT:")
print(text)
