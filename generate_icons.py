from PIL import Image

# Load the original logo
img = Image.open('static/logo.png')
w, h = img.size

# The logo is wider than it is tall (2816x1536).
# Create a square transparent background using the width as the dimension.
size = max(w, h)
new_img = Image.new("RGBA", (size, size), (255, 255, 255, 0))

# Paste the logo in the center
new_img.paste(img, ((size - w) // 2, (size - h) // 2))

# Resize and save for 192x192
icon_192 = new_img.resize((192, 192), Image.Resampling.LANCZOS)
icon_192.save('static/icon-192x192.png')

# Resize and save for 512x512
icon_512 = new_img.resize((512, 512), Image.Resampling.LANCZOS)
icon_512.save('static/icon-512x512.png')

print("Icons generated successfully!")
