import io
from pathlib import Path

import numpy as np
from PIL import Image
import streamlit as st

st.set_page_config(page_title="SPHEREx RGB Prototype", layout="wide")

st.title("SPHEREx Manual RGB Prototype")
st.write(
    "This is a simple interactive RGB composite demo using mock data. "
    "Users can adjust the red, green and blue channel weights and preview the composite image in real time."
)

BASE_DIR = Path(__file__).parent
IMG_DIR = BASE_DIR / "rgb_demo_output"

RED_PATH = IMG_DIR / "red_mock.png"
GREEN_PATH = IMG_DIR / "green_mock.png"
BLUE_PATH = IMG_DIR / "blue_mock.png"


def load_grayscale_image(path):
    img = Image.open(path).convert("L")
    arr = np.asarray(img, dtype=np.float32) / 255.0
    return arr


def normalize(arr):
    arr = np.nan_to_num(arr)
    min_val = arr.min()
    max_val = arr.max()
    if max_val - min_val == 0:
        return np.zeros_like(arr)
    return (arr - min_val) / (max_val - min_val)


def make_rgb(red, green, blue, r_weight, g_weight, b_weight, brightness):
    red = normalize(red) * r_weight
    green = normalize(green) * g_weight
    blue = normalize(blue) * b_weight

    rgb = np.stack([red, green, blue], axis=-1)
    rgb = np.clip(rgb * brightness, 0, 1)
    rgb_uint8 = (rgb * 255).astype(np.uint8)
    return Image.fromarray(rgb_uint8)


if not (RED_PATH.exists() and GREEN_PATH.exists() and BLUE_PATH.exists()):
    st.error("Mock channel images not found. Please make sure red_mock.png, green_mock.png and blue_mock.png are in rgb_demo_output/.")
    st.stop()

red_channel = load_grayscale_image(RED_PATH)
green_channel = load_grayscale_image(GREEN_PATH)
blue_channel = load_grayscale_image(BLUE_PATH)

st.sidebar.header("Channel Controls")

r_weight = st.sidebar.slider("Red Weight", 0.0, 2.0, 1.0, 0.05)
g_weight = st.sidebar.slider("Green Weight", 0.0, 2.0, 1.0, 0.05)
b_weight = st.sidebar.slider("Blue Weight", 0.0, 2.0, 1.0, 0.05)
brightness = st.sidebar.slider("Brightness", 0.2, 3.0, 1.0, 0.05)

st.sidebar.markdown("---")
st.sidebar.write("Optional: upload your own grayscale images")

uploaded_red = st.sidebar.file_uploader("Upload Red Channel", type=["png", "jpg", "jpeg"], key="red")
uploaded_green = st.sidebar.file_uploader("Upload Green Channel", type=["png", "jpg", "jpeg"], key="green")
uploaded_blue = st.sidebar.file_uploader("Upload Blue Channel", type=["png", "jpg", "jpeg"], key="blue")


def load_uploaded(uploaded_file):
    img = Image.open(uploaded_file).convert("L")
    arr = np.asarray(img, dtype=np.float32) / 255.0
    return arr


if uploaded_red is not None and uploaded_green is not None and uploaded_blue is not None:
    red_channel = load_uploaded(uploaded_red)
    green_channel = load_uploaded(uploaded_green)
    blue_channel = load_uploaded(uploaded_blue)

    if not (red_channel.shape == green_channel.shape == blue_channel.shape):
        st.error("Uploaded images must have the same dimensions.")
        st.stop()

composite = make_rgb(
    red_channel,
    green_channel,
    blue_channel,
    r_weight,
    g_weight,
    b_weight,
    brightness
)

col1, col2 = st.columns(2)

with col1:
    st.subheader("Input Channels")
    st.image((red_channel * 255).astype(np.uint8), caption="Red Channel", clamp=True)
    st.image((green_channel * 255).astype(np.uint8), caption="Green Channel", clamp=True)
    st.image((blue_channel * 255).astype(np.uint8), caption="Blue Channel", clamp=True)

with col2:
    st.subheader("RGB Composite")
    st.image(composite, caption="Composite Preview", use_container_width=True)

buffer = io.BytesIO()
composite.save(buffer, format="PNG")
buffer.seek(0)

st.download_button(
    label="Download Composite Image",
    data=buffer,
    file_name="rgb_composite_interactive.png",
    mime="image/png"
)

st.markdown("---")
st.write("Prototype status: interactive local demo complete.")