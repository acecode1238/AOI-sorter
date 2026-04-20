import cv2
import numpy as np
import tkinter as tk
from tkinter import filedialog, scrolledtext


def detect_wafer_circle(gray):
    """
    Try Hough Circle first.
    If it fails, fallback to contour + ellipse.
    Returns (x, y, radius) or None.
    """

    # --- METHOD 1: Hough Circle ---
    blur = cv2.GaussianBlur(gray, (9, 9), 2)

    circles = cv2.HoughCircles(
        blur,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=1000,
        param1=100,
        param2=40,
        minRadius=0,
        maxRadius=0
    )

    if circles is not None:
        circles = np.uint16(np.around(circles))
        x, y, r = circles[0][0]
        return int(x), int(y), int(r), "hough"

    # --- METHOD 2: fallback contour ellipse ---
    _, binary = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    kernel = np.ones((25, 25), np.uint8)
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(
        closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)

    if len(largest) < 5:
        return None

    ellipse = cv2.fitEllipse(largest)
    (cx, cy), (MA, ma), angle = ellipse

    radius = int(max(MA, ma) / 2)

    return int(cx), int(cy), radius, "ellipse"


def count_pixels():
    file_path = filedialog.askopenfilename(
        title="Select an Image",
        filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp *.tif")]
    )

    if not file_path:
        return

    img = cv2.imread(file_path)
    if img is None:
        result_box.insert(tk.END, "Error loading image.\n")
        return

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # -------- DETECT WAFER --------
    result = detect_wafer_circle(gray)

    if result is None:
        result_box.insert(tk.END, "No wafer detected.\n")
        return

    x, y, radius, method = result

    # -------- CREATE MASK --------
    mask = np.zeros(gray.shape, dtype=np.uint8)

    cv2.circle(mask, (x, y), radius, 255, -1)

    # -------- BINARY IMAGE --------
    _, binary = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    # -------- PIXEL COUNT --------
    masked = cv2.bitwise_and(binary, mask)

    white_pixels = np.count_nonzero(masked)
    total_pixels = np.count_nonzero(mask)

    black_pixels = total_pixels - white_pixels

    white_percent = (white_pixels / total_pixels) * 100
    black_percent = (black_pixels / total_pixels) * 100

    # -------- DEBUG VIEW (optional) --------
    debug = img.copy()
    cv2.circle(debug, (x, y), radius, (0, 255, 0), 3)
    cv2.circle(debug, (x, y), 5, (0, 0, 255), -1)

    # ---- FIT IMAGE TO SCREEN ----
    scale = 0.5  # adjust (0.3, 0.5, 0.7 etc.)

    debug_small = cv2.resize(debug, (0, 0), fx=scale, fy=scale)
    mask_small = cv2.resize(mask, (0, 0), fx=scale, fy=scale)

    cv2.imshow("Wafer Detection Debug (" + method + ")", debug)
    cv2.imshow("Mask", mask)

    cv2.imshow("Wafer Detection Debug (" + method + ")", debug_small)
    cv2.imshow("Mask", mask_small)
    
    cv2.waitKey(1)

    # -------- OUTPUT --------
    result_box.delete(1.0, tk.END)

    result_box.insert(
        tk.END,
        f"File: {file_path}\n"
        f"Detection method: {method}\n\n"
        f"Center: ({x}, {y})\n"
        f"Radius: {radius}\n\n"
        f"White pixels: {white_pixels}\n"
        f"Black pixels: {black_pixels}\n"
        f"Total pixels: {total_pixels}\n\n"
        f"Void % (white) {white_percent:.2f}%\n"
        f"Bonding yield (black) {black_percent:.2f}%\n"
    )


# ---------------- GUI ----------------
root = tk.Tk()
root.title("Wafer Pixel Counter")
root.geometry("900x600")

btn = tk.Button(
    root,
    text="Select Image",
    command=count_pixels,
    height=2,
    width=20,
    font=("Arial", 14)
)
btn.pack(pady=10)

result_box = scrolledtext.ScrolledText(
    root,
    width=80,
    height=25,
    font=("Consolas", 12)
)
result_box.pack(pady=10)

root.mainloop()