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

    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    #print grayscale image
    cv2.imshow("Grayscale Image", gray)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    # Convert to binary
    _, binary = cv2.threshold(
        gray,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    # Count pixels
    white_pixels = np.count_nonzero(binary) * 21.3813
    black_pixels = (binary.size * 21.3813) - white_pixels

    white_percent = (white_pixels / (binary.size * 21.3813)) * 100 
    black_percent = (black_pixels / (binary.size * 21.3813)) * 100

    # Show results
    result_box.delete(1.0, tk.END)

    result_box.insert(
        tk.END,
        f"File: {file_path}\n\n"
        f"White pixels: {white_pixels:.0f}\n"
        f"Black pixels: {black_pixels:.0f}\n"
        f"Total pixels: {binary.size * 21.3813:.0f}\n\n"
        f"White %: {white_percent:.2f}%\n"
        f"Black %: {black_percent:.2f}%\n"
    )


# GUI setup
root = tk.Tk()
root.title("Pixel Counter")

# Bigger window
root.geometry("900x600")

# Button
btn = tk.Button(
    root,
    text="Select Image",
    command=count_pixels,
    height=2,
    width=20,
    font=("Arial", 14)
)

btn.pack(pady=10)

# Large results box
result_box = scrolledtext.ScrolledText(
    root,
    width=80,
    height=25,
    font=("Consolas", 14)
)

result_box.pack(pady=10)

root.mainloop()