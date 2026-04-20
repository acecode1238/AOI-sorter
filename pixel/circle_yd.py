import cv2
import numpy as np
import tkinter as tk
from tkinter import filedialog, scrolledtext

def count_pixels():
    file_path = filedialog.askopenfilename(
        title="Select an Image",
        filetypes=[
            ("Image Files", "*.png *.jpg *.jpeg *.bmp *.tif"),
            ("All Files", "*.*")
        ]
    )

    if not file_path:
        return

    img = cv2.imread(file_path)

    if img is None:
        result_box.insert(tk.END, "Error loading image.\n")
        return

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # -------- MAKE WAFER WHITE --------

    _, binary = cv2.threshold(
        gray,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    # Fill gaps inside wafer
    kernel = np.ones((25, 25), np.uint8)

    closed = cv2.morphologyEx(
        binary,
        cv2.MORPH_CLOSE,
        kernel
    )

    # -------- FIND LARGEST CONTOUR --------

    contours, _ = cv2.findContours(
        closed,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    if not contours:
        result_box.insert(tk.END, "No wafer detected.\n")
        return

    largest_contour = max(contours, key=cv2.contourArea)

    # -------- CREATE MASK --------

    mask = np.zeros(gray.shape, dtype=np.uint8)

    cv2.drawContours(
        mask,
        [largest_contour],
        -1,
        255,
        thickness=-1
    )

    # -------- COUNT PIXELS --------

    masked_binary = cv2.bitwise_and(binary, mask)

    white_pixels = np.count_nonzero(masked_binary)

    total_pixels = np.count_nonzero(mask)

    black_pixels = total_pixels - white_pixels

    white_percent = (white_pixels / total_pixels) * 100
    black_percent = (black_pixels / total_pixels) * 100

    # -------- SHOW RESULTS --------

    result_box.delete(1.0, tk.END)

    result_box.insert(
        tk.END,
        f"File: {file_path}\n\n"
        f"Pixels INSIDE wafer only:\n\n"
        f"White pixels: {white_pixels}\n"
        f"Black pixels: {black_pixels}\n"
        f"Total pixels (wafer only): {total_pixels}\n\n"
        f"White %: {white_percent:.2f}%\n"
        f"Black %: {black_percent:.2f}%\n"
    )


# GUI
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
    font=("Consolas", 14)
)

result_box.pack(pady=10)

root.mainloop()