import cv2
import numpy as np
import tkinter as tk
from tkinter import filedialog, scrolledtext

# -------- GLOBAL STATE --------
points = []
drawing_done = False

zoom = 1.0
offset_x = 0
offset_y = 0

dragging = False
drag_start = (0, 0)

click_start = (0, 0)
moved = False

# Fixed viewport size (prevents stretching)
VIEW_W = 1000
VIEW_H = 700


# -------- MOUSE CALLBACK --------
def mouse_callback(event, x, y, flags, param):
    global points, drawing_done
    global zoom, offset_x, offset_y
    global dragging, drag_start
    global moved

    img_x = int((x + offset_x) / zoom)
    img_y = int((y + offset_y) / zoom)

    if event == cv2.EVENT_LBUTTONDOWN:
        dragging = True
        drag_start = (x, y)
        moved = False

    elif event == cv2.EVENT_MOUSEMOVE:

        if dragging:
            dx = x - drag_start[0]
            dy = y - drag_start[1]

            if abs(dx) > 3 or abs(dy) > 3:
                moved = True

            offset_x -= dx
            offset_y -= dy

            drag_start = (x, y)

    elif event == cv2.EVENT_LBUTTONUP:

        dragging = False

        if not moved:
            points.append((img_x, img_y))

    elif event == cv2.EVENT_RBUTTONDOWN:
        drawing_done = True

    elif event == cv2.EVENT_MOUSEWHEEL:

        old_zoom = zoom

        if flags > 0:
            zoom *= 1.2
        else:
            zoom /= 1.2

        zoom = max(0.1, min(zoom, 15))

        offset_x = int((x + offset_x) * (zoom / old_zoom) - x)
        offset_y = int((y + offset_y) * (zoom / old_zoom) - y)


# -------- MAIN FUNCTION --------
def count_pixels():

    global points, drawing_done
    global zoom, offset_x, offset_y

    points = []
    drawing_done = False

    zoom = 1.0
    offset_x = 0
    offset_y = 0

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

    cv2.namedWindow("Draw Region", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Draw Region", VIEW_W, VIEW_H)

    cv2.setMouseCallback("Draw Region", mouse_callback)

    while True:

        key = cv2.waitKeyEx(1)

        pan_speed = int(40 / zoom)

        # Arrow keys pan
        if key == 2424832:
            offset_x -= pan_speed

        elif key == 2555904:
            offset_x += pan_speed

        elif key == 2490368:
            offset_y -= pan_speed

        elif key == 2621440:
            offset_y += pan_speed

        elif key == ord('z'):
            if len(points) > 0:
                points.pop()

        elif key == 27:
            cv2.destroyAllWindows()
            return

        # Resize image
        resized = cv2.resize(
            img,
            None,
            fx=zoom,
            fy=zoom,
            interpolation=cv2.INTER_LINEAR
        )

        rh, rw = resized.shape[:2]

        # Clamp offsets
        max_x = max(0, rw - VIEW_W)
        max_y = max(0, rh - VIEW_H)

        offset_x = max(0, min(offset_x, max_x))
        offset_y = max(0, min(offset_y, max_y))

        end_x = offset_x + VIEW_W
        end_y = offset_y + VIEW_H

        view = resized[
            offset_y:end_y,
            offset_x:end_x
        ].copy()

        # Draw polygon
        if len(points) > 1:

            scaled_points = []

            for px, py in points:

                sx = int(px * zoom - offset_x)
                sy = int(py * zoom - offset_y)

                scaled_points.append((sx, sy))

            cv2.polylines(
                view,
                [np.array(scaled_points)],
                False,
                (0, 255, 0),
                2
            )

        # Draw points
        for px, py in points:

            sx = int(px * zoom - offset_x)
            sy = int(py * zoom - offset_y)

            cv2.circle(
                view,
                (sx, sy),
                4,
                (0, 0, 255),
                -1
            )

        cv2.imshow("Draw Region", view)

        if drawing_done:
            break

    cv2.destroyAllWindows()

    if len(points) < 3:
        result_box.insert(
            tk.END,
            "Not enough points drawn.\n"
        )
        return

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    _, binary = cv2.threshold(
        gray,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    mask = np.zeros(gray.shape, dtype=np.uint8)

    cv2.fillPoly(mask, [np.array(points)], 255)

    masked = cv2.bitwise_and(binary, mask)

    white = np.count_nonzero(masked)
    total = np.count_nonzero(mask)
    black = total - white

    white_pct = (white / total) * 100
    black_pct = (black / total) * 100

    result_box.delete(1.0, tk.END)

    result_box.insert(
        tk.END,
        f"File: {file_path}\n\n"
        f"White pixels: {white}\n"
        f"Black pixels: {black}\n"
        f"Total pixels: {total}\n\n"
        f"White %: {white_pct:.2f}%\n"
        f"Black %: {black_pct:.2f}%\n"
    )


# -------- GUI --------
root = tk.Tk()

root.title("Zoom + Pan + Draw Pixel Counter")

root.geometry("900x600")

btn = tk.Button(
    root,
    text="Select Image and Draw Region",
    command=count_pixels,
    height=2,
    width=30,
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