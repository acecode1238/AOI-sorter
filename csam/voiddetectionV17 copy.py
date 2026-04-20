import cv2
import numpy as np
import tkinter as tk
from tkinter import filedialog
from tkinter import scrolledtext
from PIL import Image, ImageTk
import csv
import os
import threading
import queue


box_width = 1000
box_height = 1000
min_box_size = 10
max_box_width = 5000
max_box_height = 5000
scale = 1.0
box_x, box_y = 60, 60
offset_x, offset_y = 0, 0
dragging_box = False
dragging_image = False
prev_mouse_x, prev_mouse_y = -1, -1
inset_margin_width = 10  
inset_margin_height = 10  
cached_scale = None
cached_canvas = None
display_window = "C2W Void Analyzer"
box_speed = 30
highlight_inset = False
selected_file_path = None
threshold_pct = 10.0
WHITE_THRESHOLD = 60
image = None
gray = None
display_width = 1200
display_height = 900
final_results = []  
tk_root = None
stats_win = None
stats_text = None
frozen_box_x = None
frozen_box_y = None
analysis_running = False
analysis_thread = None
arrow_mode = "roi"




ui_queue = queue.Queue()


def imshow_letterbox(win, img, win_w, win_h):
    h, w = img.shape[:2]
    if h == 0 or w == 0:
        return

    scale = min(win_w / w, win_h / h)
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))

    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_NEAREST)

    canvas = np.zeros((win_h, win_w, 3), dtype=np.uint8)
    x0 = (win_w - new_w) // 2
    y0 = (win_h - new_h) // 2
    canvas[y0:y0+new_h, x0:x0+new_w] = resized

    cv2.imshow(win, canvas)



def clamp_offsets():
    global offset_x, offset_y
    if image is None:
        return

    max_left = 0
    max_top = 0
    min_left = -(image.shape[1] * scale - display_width)
    min_top  = -(image.shape[0] * scale - display_height)

    
    if min_left > 0: min_left = 0
    if min_top > 0:  min_top = 0

    offset_x = int(np.clip(offset_x, min_left, max_left))
    offset_y = int(np.clip(offset_y, min_top, max_top))


def center_view_on_roi():
    global offset_x, offset_y
    if image is None:
        return

    roi_cx = (box_x + box_width / 2.0) * scale
    roi_cy = (box_y + box_height / 2.0) * scale

    
    offset_x = int(display_width / 2 - roi_cx)
    offset_y = int(display_height / 2 - roi_cy)

    clamp_offsets()



def get_threshold_pct():
    global threshold_pct
    try:
        return float(threshold_pct)
    except Exception:
        return 10.0

def post_stats_to_gui(lines, title="Chip Pixel Statistics"):
    ui_queue.put((title, lines))

def poll_ui_queue():
    try:
        while True:
            title, lines = ui_queue.get_nowait()
            show_stats_gui(lines, title=title)
    except queue.Empty:
        pass

    if tk_root is not None:
        tk_root.after(100, poll_ui_queue)


def show_stats_gui(lines, title="Chip Pixel Statistics"):
    global stats_win, stats_text, tk_root

    if tk_root is None:
        return

    if stats_win is None or (not stats_win.winfo_exists()):
        stats_win = tk.Toplevel(tk_root)
        stats_win.title(title)
        stats_win.geometry("900x600")

        stats_text = scrolledtext.ScrolledText(
            stats_win, wrap="none", font=("Consolas", 11)
        )
        stats_text.pack(fill="both", expand=True, padx=10, pady=10)

        
        stats_text.tag_configure("over", background="#FFF59D")

    else:
        stats_win.title(title)

    
    stats_text.config(state="normal")
    stats_text.delete("1.0", "end")

    for line in lines:
        start = stats_text.index("end-1c")
        stats_text.insert("end", line + "\n")
        end = stats_text.index("end-1c")

        if "[OVER THRESHOLD]" in line:
            stats_text.tag_add("over", start, end)

    stats_text.config(state="disabled")

    
    try:
        stats_win.lift()
        stats_win.attributes("-topmost", True)
        stats_win.attributes("-topmost", False)
    except Exception:
        pass

    try:
        stats_win.bell()
    except Exception:
        pass

    try:
        stats_win.after(0, stats_win.focus_force)
    except Exception:
        pass

    stats_win.title(f"{title}  ✅ Updated")
    stats_win.after(800, lambda: stats_win.winfo_exists() and stats_win.title(title))




def save_results_to_csv(results, box_x, box_y,
                        inset_margin_width=5, inset_margin_height=5):
    """Save per-chip statistics and a summary section in a single CSV file."""

    chips_blue_over_10 = 0
    chips_purple_over_10 = 0

    if not results:
        return

    file_path = filedialog.asksaveasfilename(
        defaultextension=".csv",
        filetypes=[("CSV files", "*.csv")],
        title="Save Chip Void Statistics"
    )
    if not file_path:
        return

    with open(file_path, "w", newline="") as f:
        writer = csv.writer(f)

        writer.writerow([
            "Chip_ID",
            "Void % (Blue)", "White pixel (Blue)", "Black pixel (Blue)",
            "Void % (Purple)", "White pixel (Purple)", "Black pixel (Purple)"
        ])

        total_white_blue = 0
        total_black_blue = 0
        total_white_purple = 0
        total_black_purple = 0

        zero_blue = 0
        zero_purple = 0

        chips_with_side_voids = 0
        chips_with_purple_edge_voids = 0  

        for i, res in enumerate(results, start=1):
            x, y, w, h = res["bounding_box"]

            
            white_blue = res["white_pixels_bbox"]
            black_blue = res["black_pixels_bbox"]
            total_blue = white_blue + black_blue
            pct_blue = (white_blue / total_blue * 100) if total_blue > 0 else 0

            
            roi_gray_blue = gray[box_y + y : box_y + y + h,
                                 box_x + x : box_x + x + w]
            binary_white_local = cv2.inRange(roi_gray_blue, WHITE_THRESHOLD, 255)
            white_coords_local = np.column_stack(np.where(binary_white_local > 0))

            for (py, px) in white_coords_local:
                if px == 0 or px == w - 1 or py == 0 or py == h - 1:
                    chips_with_side_voids += 1
                    break

            total_white_blue += white_blue
            total_black_blue += black_blue
            if white_blue == 0:
                zero_blue += 1

            
            inset_x1 = box_x + x + inset_margin_width
            inset_y1 = box_y + y + inset_margin_height
            inset_x2 = box_x + x + w - inset_margin_width
            inset_y2 = box_y + y + h - inset_margin_height

            if inset_x2 <= inset_x1 or inset_y2 <= inset_y1:
                white_purple = 0
                black_purple = 0
                pct_purple = 0
                purple_edge_void = False
            else:
                roi_gray = gray[inset_y1:inset_y2, inset_x1:inset_x2]
                binary_white = cv2.inRange(roi_gray, WHITE_THRESHOLD, 255)

                white_purple = int(cv2.countNonZero(binary_white))
                total_purple = roi_gray.size
                black_purple = total_purple - white_purple
                pct_purple = (white_purple / total_purple * 100) if total_purple > 0 else 0

                
                purple_edge_void = False
                num_labels, labels = cv2.connectedComponents(binary_white)
                roi_h, roi_w = binary_white.shape

                for label in range(1, num_labels):
                    ys, xs = np.where(labels == label)
                    if len(xs) == 0:
                        continue
                    if (
                        0 in xs or (roi_w - 1) in xs or
                        0 in ys or (roi_h - 1) in ys
                    ):
                        purple_edge_void = True
                        chips_with_purple_edge_voids += 1
                        break
            thr = get_threshold_pct()

            if pct_blue > thr:
                chips_blue_over_10 += 1
            if pct_purple > thr:
                chips_purple_over_10 += 1

            total_white_purple += white_purple
            total_black_purple += black_purple
            if white_purple == 0:
                zero_purple += 1

            
            writer.writerow([
                i,
                f"{pct_blue:.3f}", white_blue, black_blue,
                f"{pct_purple:.3f}", white_purple, black_purple
            ])

        
        writer.writerow([])
        writer.writerow([])
        writer.writerow(["Chips with inner void", len(results) - zero_purple])
        writer.writerow([])

        
        writer.writerow(["Summary (Blue)"])
        writer.writerow(["Total Chips", len(results)])
        writer.writerow(["Zero Void Chips (Blue)", zero_blue])
        writer.writerow(["Chips with edge voids (Blue)", chips_with_side_voids])
        writer.writerow([f"Chips with void > {thr}% (Blue)", chips_blue_over_10])
        writer.writerow(["Total White Pixels (Blue)", total_white_blue])
        writer.writerow(["Total Black Pixels (Blue)", total_black_blue])
        overall_blue = (total_white_blue / (total_white_blue + total_black_blue) * 100
                        if (total_white_blue + total_black_blue) else 0)
        writer.writerow(["Overall Void % (Blue)", f"{overall_blue:.3f}"])

        
        writer.writerow([])
        writer.writerow(["Summary (Purple)"])
        writer.writerow(["Total Chips", len(results)])
        writer.writerow(["Zero Void Chips (Purple)", zero_purple])
        writer.writerow(["Chips with edge voids (Purple)", chips_with_purple_edge_voids])
        writer.writerow([f"Chips with void > {thr}% (Purple)", chips_purple_over_10])
        writer.writerow(["Total White Pixels (Purple)", total_white_purple])
        writer.writerow(["Total Black Pixels (Purple)", total_black_purple])
        overall_purple = (total_white_purple /
                          (total_white_purple + total_black_purple) * 100
                          if (total_white_purple + total_black_purple) else 0)
        writer.writerow(["Overall Void % (Purple)", f"{overall_purple:.3f}"])


def find_white_in_black_shapes(roi_gray, WHITE_THRESHOLD=40):
    # 1. Create binary maps
    _, binary_inv = cv2.threshold(roi_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    _, binary_white = cv2.threshold(roi_gray, WHITE_THRESHOLD, 255, cv2.THRESH_BINARY)

    # Clean up background noise
    kernel_clean = np.ones((3,3), np.uint8)
    binary_inv = cv2.morphologyEx(binary_inv, cv2.MORPH_OPEN, kernel_clean)

    # 2. SEPARATION: Use a fixed threshold for distance transform seeds
    dist_transform = cv2.distanceTransform(binary_inv, cv2.DIST_L2, 5)
    _, sure_fg = cv2.threshold(dist_transform, 4, 255, 0) # Fixed 4-pixel seed
    
    sure_fg = np.uint8(sure_fg)
    _, markers = cv2.connectedComponents(sure_fg)
    markers = markers + 1
    
    sure_bg = cv2.dilate(binary_inv, kernel_clean, iterations=2)
    unknown = cv2.subtract(sure_bg, sure_fg)
    markers[unknown == 255] = 0

    # 3. WATERSHED
    roi_color = cv2.cvtColor(roi_gray, cv2.COLOR_GRAY2BGR)
    markers = cv2.watershed(roi_color, markers)

    # --- STEP 4: MEDIAN FILTERING (The "Big Box" Fix) ---
    raw_results = []
    all_widths = []
    all_heights = []
    unique_markers = np.unique(markers)

    for m_id in unique_markers:
        if m_id <= 1: continue 
        
        chip_mask = np.uint8(markers == m_id)
        cnts, _ = cv2.findContours(chip_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts: continue
        
        x, y, w, h = cv2.boundingRect(cnts[0])
        # Only collect dimensions of things that look like potential chips
        if w > 5 and h > 5:
            all_widths.append(w)
            all_heights.append(h)
            raw_results.append((x, y, w, h, cnts[0]))

    if not all_widths: return []

    # Calculate typical chip size
    med_w = np.median(all_widths)
    med_h = np.median(all_heights)

    results = []
    for x, y, w, h, cnt in raw_results:
        # IGNORE logic: Discard if it's 50% bigger or 50% smaller than a normal chip
        if w > med_w * 1.4 or w < med_w * 0.6:
            continue
        if h > med_h * 1.4 or h < med_h * 0.6:
            continue

        # Accuracy Fix: Inset slightly
        inset = 1
        ix, iy, iw, ih = x+inset, y+inset, w-(inset*2), h-(inset*2)
        if iw <= 0 or ih <= 0: continue

        clean_mask = np.zeros(roi_gray.shape, dtype=np.uint8)
        cv2.rectangle(clean_mask, (ix, iy), (ix + iw, iy + ih), 255, -1)

        white_pixels_contour = np.sum(np.logical_and(clean_mask == 255, binary_white == 255))
        total_pixels_contour = cv2.countNonZero(clean_mask)

        results.append({
            "type": "Square" if 0.8 <= iw/ih <= 1.2 else "Rectangle",
            "white_pixels_contour": int(white_pixels_contour),
            "total_pixels_contour": int(total_pixels_contour),
            "percent_white_contour": round(100 * white_pixels_contour / total_pixels_contour, 3),
            "white_pixels_bbox": int(white_pixels_contour),
            "total_pixels_bbox": int(total_pixels_contour),
            "percent_white_bbox": round(100 * white_pixels_contour / total_pixels_contour, 3),
            "black_pixels_bbox": int(total_pixels_contour - white_pixels_contour),
            "bounding_box": (ix, iy, iw, ih),
            "contour": cnt,
        })

    return results


def show_chip_statistics(results, box_x, box_y,
                         highlight_inset=False,
                         inset_margin_width=5,
                         inset_margin_height=5):
    total_white = 0
    total_black = 0
    total_pixels = 0
    zero_white_count = 0
    chips_with_side_voids = 0
    chips_over_10 = 0

    
    chips_with_purple_edge_voids = 0

    for res in results:
        x, y, w, h = res["bounding_box"]

        if highlight_inset:  
            inset_x1 = box_x + x + inset_margin_width
            inset_y1 = box_y + y + inset_margin_height
            inset_x2 = box_x + x + w - inset_margin_width
            inset_y2 = box_y + y + h - inset_margin_height

            roi_gray = gray[inset_y1:inset_y2, inset_x1:inset_x2]
            if roi_gray.size == 0:
                continue

            binary_white = cv2.inRange(roi_gray, WHITE_THRESHOLD, 255)
            white_px = cv2.countNonZero(binary_white)
            total_px = roi_gray.size
            black_px = total_px - white_px

            
            num_labels, labels = cv2.connectedComponents(binary_white)

            roi_h, roi_w = binary_white.shape

            purple_edge_void = False

            for label in range(1, num_labels):  
                ys, xs = np.where(labels == label)

                if len(xs) == 0:
                    continue

                if (
                    0 in xs or (roi_w - 1) in xs or
                    0 in ys or (roi_h - 1) in ys
                ):
                    purple_edge_void = True
                    break

            if purple_edge_void:
                chips_with_purple_edge_voids += 1

        else:
            
            white_px = res["white_pixels_bbox"]
            black_px = res["black_pixels_bbox"]
            total_px = res["total_pixels_bbox"]

            
            roi_gray_blue = gray[box_y + y : box_y + y + h,
                                 box_x + x : box_x + x + w]
            binary_white_local = cv2.inRange(roi_gray_blue, WHITE_THRESHOLD, 255)
            white_coords_local = np.column_stack(np.where(binary_white_local > 0))

            for (py, px) in white_coords_local:
                if px == 0 or px == w - 1 or py == 0 or py == h - 1:
                    chips_with_side_voids += 1
                    break

        
        if total_px > 0:
            pct = (white_px / total_px) * 100
            thr = get_threshold_pct()
            if pct > thr:
                chips_over_10 += 1

        total_white += white_px
        total_black += black_px
        total_pixels += total_px

        if white_px == 0:
            zero_white_count += 1

    overall_white_pct = (total_white / total_pixels) * 100 if total_pixels > 0 else 0
    mode_label = "Purple Box (edge exclusion)" if highlight_inset else "Blue Box"

    lines = [
        f"Summary Mode: {mode_label}",
        f"Total Chips: {len(results)}",
        f"Chips with 0 voids: {zero_white_count}",
        f"Total White Pixels: {total_white}",
        f"Total Black Pixels: {total_black}",
        f"Overall Void %: {overall_white_pct:.2f}%",
    ]

    if not highlight_inset:
        lines.append(f"Chips with edge voids/defect (Blue): {chips_with_side_voids}")
    else:
        lines.append(f"Chips with edge voids/defect (Purple): {chips_with_purple_edge_voids}")

    lines.append(f"Chips with void > {thr:.2f}%: {chips_over_10}")

    width = 1000
    height = 30 * (len(lines) + 1)
    img = np.zeros((height, width, 3), dtype=np.uint8)
    for i, line in enumerate(lines):
        y = 30 + i * 30
        cv2.putText(img, line, (10, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (255, 255, 255), 2)
        
    post_stats_to_gui(lines, title="Chip Statistics Summary")


def mouse_callback(event, x, y, flags, param):
    global dragging_box, dragging_image, prev_mouse_x, prev_mouse_y
    global box_x, box_y, offset_x, offset_y, scale

    if image is None:
        return

    
    if event == cv2.EVENT_LBUTTONDOWN:
        prev_mouse_x, prev_mouse_y = x, y
        dragging_box = True

    elif event == cv2.EVENT_MOUSEMOVE and dragging_box:
        dx = (x - prev_mouse_x) / scale
        dy = (y - prev_mouse_y) / scale

        box_x = int(np.clip(box_x + dx, 0, image.shape[1] - box_width))
        box_y = int(np.clip(box_y + dy, 0, image.shape[0] - box_height))

        prev_mouse_x, prev_mouse_y = x, y

    elif event == cv2.EVENT_LBUTTONUP:
        dragging_box = False

    
    elif event == cv2.EVENT_RBUTTONDOWN:
        prev_mouse_x, prev_mouse_y = x, y
        dragging_image = True

    elif event == cv2.EVENT_MOUSEMOVE and dragging_image:
        dx = x - prev_mouse_x
        dy = y - prev_mouse_y

        max_left = 0
        max_top = 0
        min_left = -(image.shape[1] * scale - display_width)
        min_top  = -(image.shape[0] * scale - display_height)
        if min_left > 0: min_left = 0
        if min_top > 0:  min_top = 0

        offset_x = int(np.clip(offset_x + dx, min_left, max_left))
        offset_y = int(np.clip(offset_y + dy, min_top, max_top))

        prev_mouse_x, prev_mouse_y = x, y

    elif event == cv2.EVENT_RBUTTONUP:
        dragging_image = False

   
    elif event == cv2.EVENT_MOUSEWHEEL:
        old_scale = scale
        scale = min(max(scale + 0.1 if flags > 0 else scale - 0.1, 0.2), 5.0)

        mx, my = x, y
        offset_x = int(mx - (mx - offset_x) * scale / old_scale)
        offset_y = int(my - (my - offset_y) * scale / old_scale)

        
        max_left = 0
        max_top = 0
        min_left = -(image.shape[1] * scale - display_width)
        min_top  = -(image.shape[0] * scale - display_height)
        if min_left > 0: min_left = 0
        if min_top > 0:  min_top = 0

        offset_x = int(np.clip(offset_x, min_left, max_left))
        offset_y = int(np.clip(offset_y, min_top, max_top))


def show_stats_popup(results, box_x, box_y,
                     highlight_inset=False,
                     inset_margin_width=5,
                     inset_margin_height=5):
    thr = get_threshold_pct()
    lines = []
    mode_label = "Purple" if highlight_inset else "Blue"

    for i, res in enumerate(results, start=1):
        x, y, w, h = res["bounding_box"]

        if highlight_inset:
            
            inset_x1 = x + inset_margin_width
            inset_y1 = y + inset_margin_height
            inset_x2 = x + w - inset_margin_width
            inset_y2 = y + h - inset_margin_height

            abs_inset_x1 = box_x + inset_x1
            abs_inset_y1 = box_y + inset_y1
            abs_inset_x2 = box_x + inset_x2
            abs_inset_y2 = box_y + inset_y2

            if abs_inset_x2 <= abs_inset_x1 or abs_inset_y2 <= abs_inset_y1:
                white_px_inset = 0
                black_px_inset = 0
                pct_white_inset = 0.0
            else:
                roi_gray = gray[abs_inset_y1:abs_inset_y2,
                                abs_inset_x1:abs_inset_x2]
                binary_white = cv2.inRange(roi_gray, WHITE_THRESHOLD, 255)
                white_px_inset = cv2.countNonZero(binary_white)
                total_pixels_inset = roi_gray.size
                black_px_inset = total_pixels_inset - white_px_inset
                pct_white_inset = (white_px_inset / total_pixels_inset * 100
                                   ) if total_pixels_inset > 0 else 0.0
            over = " [OVER THRESHOLD]" if pct_white_inset > thr else ""

            lines.append(
                f"Chip {i}: Void % ({mode_label}) = {pct_white_inset:.2f}% {over}, " 
                f"White Pixels = {white_px_inset}, Black Pixels = {black_px_inset}"
            )
        else:
            
            white_px_bbox = res["white_pixels_bbox"]
            black_px_bbox = res["black_pixels_bbox"]
            pct_bbox = res["percent_white_bbox"]
            over = " [OVER THRESHOLD]" if pct_bbox > thr else ""

            lines.append(
                f"Chip {i}: Void % ({mode_label}) = {pct_bbox:.2f}% {over}, "
                f"White Pixels = {white_px_bbox}, Black Pixels = {black_px_bbox}"
            )

    if not lines:
        lines = ["No chips detected."]

    post_stats_to_gui(lines, title="Chip Pixel Statistics")




def show_controls_popup():
    controls = [
        "CONTROL Panel",
        "----------------------------------------",
        "W / A / S / D         :Move ROI box",
        "Mouse wheel           :Zoom in/out",
        "[ and ]               :Resize ROI box width",
        "{ and }               :Resize ROI box height",
        "+ / -                 :Increase/decrease move ROI box speed",
        "I/K                   :Increase / Decrease inset width",
        "U/J                   :Increase / Decrease inset height",
        "R                     :Reset ROI box",
        "Enter                 :Detect white-in-black chips and refreshes results",
        "Tab                   :Show overall chip statistics and refreshes results",
        "Esc                   :Exit",
        "T                     :Toggle between blue/purple box",
        "P                     :Save chip result as csv file",
        "Arrow keys            :Move ROI with image",
        "Right click and drag  :Move image",
        "Left click and drag   :Move ROI box"
    ]

    width = 700
    height = 30 + 25 * len(controls)
    help_img = np.zeros((height, width, 3), dtype=np.uint8)

    for i, line in enumerate(controls):
        y = 30 + i * 25
        cv2.putText(help_img, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

    cv2.imshow("Controls", help_img)

def overlay_mask(background, mask, roi_x, roi_y, scale, offset_x, offset_y,
                 display_width, display_height):
    if mask is None or mask.size == 0:
        return

    h, w = mask.shape

    
    disp_w = max(1, int(w * scale))
    disp_h = max(1, int(h * scale))
    m = cv2.resize(mask, (disp_w, disp_h), interpolation=cv2.INTER_NEAREST)

    
    bx1 = int(roi_x * scale + offset_x)
    by1 = int(roi_y * scale + offset_y)
    bx2 = bx1 + disp_w
    by2 = by1 + disp_h

    
    x1 = max(bx1, 0)
    y1 = max(by1, 0)
    x2 = min(bx2, display_width)
    y2 = min(by2, display_height)
    if x2 <= x1 or y2 <= y1:
        return

    mx1 = x1 - bx1
    my1 = y1 - by1
    mx2 = mx1 + (x2 - x1)
    my2 = my1 + (y2 - y1)

    roi = background[y1:y2, x1:x2]
    mroi = m[my1:my2, mx1:mx2]

    
    roi[mroi > 0] = (0, 255, 255)



def draw_and_show():
    global cached_scale, cached_canvas
    global display_width, display_height

    if image is None or gray is None or white_mask_full is None:
        return

    if cached_scale != scale or cached_canvas is None:
        resized = cv2.resize(image, None, fx=scale, fy=scale)
        gray_resized = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        _, bw = cv2.threshold(gray_resized, 127, 255, cv2.THRESH_BINARY)
        cached_canvas = cv2.cvtColor(bw, cv2.COLOR_GRAY2BGR)
        cached_scale = scale

    canvas = cached_canvas

    
    try:
        _, _, display_width, display_height = cv2.getWindowImageRect(display_window)
    except Exception:
        pass

    background = np.zeros((display_height, display_width, 3), dtype=np.uint8)

    
    try:
        _, _, wwin, hwin = cv2.getWindowImageRect(display_window)
        if wwin > 0 and hwin > 0:
            display_width, display_height = wwin, hwin
    except Exception:
        pass

    background = np.zeros((display_height, display_width, 3), dtype=np.uint8)

    x_offset, y_offset = offset_x, offset_y

   
    x1 = max(x_offset, 0)
    y1 = max(y_offset, 0)

    
    img_x1 = max(-x_offset, 0)
    img_y1 = max(-y_offset, 0)

    
    copy_w = min(canvas.shape[1] - img_x1, display_width - x1)
    copy_h = min(canvas.shape[0] - img_y1, display_height - y1)

    x2 = x1 + max(0, copy_w)
    y2 = y1 + max(0, copy_h)
    img_x2 = img_x1 + max(0, copy_w)
    img_y2 = img_y1 + max(0, copy_h)

    if copy_w > 0 and copy_h > 0:
        background[y1:y2, x1:x2] = canvas[img_y1:img_y2, img_x1:img_x2]


        scaled_box_x = int(box_x * scale) + offset_x
        scaled_box_y = int(box_y * scale) + offset_y
        scaled_box_width = int(box_width * scale)
        scaled_box_height = int(box_height * scale)
        cv2.rectangle(background,
                    (scaled_box_x, scaled_box_y),
                    (scaled_box_x + scaled_box_width, scaled_box_y + scaled_box_height),
                    (0, 255, 0), 2)
        


    if final_results:
     for idx, res in enumerate(final_results, start=1):
        x, y, w, h = res["bounding_box"]
        bx0 = frozen_box_x if frozen_box_x is not None else box_x
        by0 = frozen_box_y if frozen_box_y is not None else box_y

        abs_x = bx0 + x
        abs_y = by0 + y


        top_left = (int(abs_x * scale + offset_x), int(abs_y * scale + offset_y))
        bottom_right = (int((abs_x + w) * scale + offset_x), int((abs_y + h) * scale + offset_y))
        x1, y1 = top_left
        x2, y2 = bottom_right
        if x2 < 0 or y2 < 0 or x1 > display_width or y1 > display_height:
            continue

        inset_x1 = abs_x + inset_margin_width
        inset_y1 = abs_y + inset_margin_height
        inset_x2 = abs_x + w - inset_margin_width
        inset_y2 = abs_y + h - inset_margin_height

        inset_top_left = (int(inset_x1 * scale + offset_x), int(inset_y1 * scale + offset_y))
        inset_bottom_right = (int(inset_x2 * scale + offset_x), int(inset_y2 * scale + offset_y))


        cv2.rectangle(background, top_left, bottom_right, (255, 0, 0), 2)
        cv2.rectangle(background, inset_top_left, inset_bottom_right, (255, 0, 255), 1)
        

        if highlight_inset:
            roi_x, roi_y = inset_x1, inset_y1
            roi_w, roi_h = inset_x2 - inset_x1, inset_y2 - inset_y1
        else:
            roi_x, roi_y = abs_x, abs_y
            roi_w, roi_h = w, h

        
        if roi_w <= 0 or roi_h <= 0:
            continue

        binary_white = white_mask_full[roi_y:roi_y + roi_h, roi_x:roi_x + roi_w]

        if binary_white.size == 0:
            continue

        total_px = int(binary_white.size)
        white_px = int(cv2.countNonZero(binary_white))
        void_pct = (white_px / total_px * 100.0) if total_px > 0 else 0.0

        mode_text = "purple" if highlight_inset else "blue"

        chip_label = f"C{idx}|{mode_text[0].upper()} void %:{void_pct:.2f}"
        
        tx = top_left[0] + 3
        ty = top_left[1] - 10
        

        
        cv2.putText(background, chip_label, (tx , ty),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 255), 1)

        white_count = cv2.countNonZero(binary_white)
        if white_count == 0:
            cv2.rectangle(background, top_left, bottom_right, (0, 255, 0), 3)

        overlay_mask(background, binary_white, roi_x, roi_y,
             scale, offset_x, offset_y, display_width, display_height)


       

    cv2.imshow(display_window, background)



def cv_imread_unicode(path):
        data = np.fromfile(path, dtype=np.uint8)     
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)   
        return img



def main1():
    
    global image, gray, box_x, box_y, box_speed, box_width, box_height, display_width, display_height, max_box_size, final_results
    global highlight_inset
    global inset_margin_width, inset_margin_height
    global white_mask_full
    global frozen_box_x, frozen_box_y
    global arrow_mode
    
    if not selected_file_path:
        print("ERROR: No file selected")
        return

    print("selected_file_path =", repr(selected_file_path))
    print("exists =", os.path.exists(selected_file_path))

    image = cv_imread_unicode(selected_file_path)
    if image is None:
        print("ERROR: Failed to load image with OpenCV:", selected_file_path)
        return


    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    max_box_size = min(image.shape[0], image.shape[1])
    white_mask_full = cv2.inRange(gray, WHITE_THRESHOLD, 255)

    cv2.namedWindow(display_window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(display_window, 1200, 900)
    cv2.setMouseCallback(display_window, mouse_callback)
    show_controls_popup()

    

    while True:
        draw_and_show()
        key = cv2.waitKeyEx(30)
        step = box_speed
        KEY_LEFT  = 2424832
        KEY_UP    = 2490368
        KEY_RIGHT = 2555904
        KEY_DOWN  = 2621440
        if cv2.getWindowProperty(display_window, cv2.WND_PROP_VISIBLE) < 1:
         break

        if key == ord('+') or key == ord('='):
            box_speed = min(box_speed + 1, 100)
        elif key == ord('-'):
            box_speed = max(box_speed - 1, 2)
        if key == ord(']'):
            new_width = box_width + 5
            if new_width <= max_box_width and box_x + new_width <= image.shape[1]:
                box_width = new_width

        if key == ord('['):
            new_width = box_width - 5
            if new_width >= min_box_size:
                box_width = new_width

        if key == ord('}'):
            new_height = box_height + 5
            if new_height <= max_box_height and box_y + new_height <= image.shape[0]:
                box_height = new_height

        if key == ord('t'):
            highlight_inset = not highlight_inset
            mode = "Inset (purple)" if highlight_inset else "Bounding (blue)"

        if key == ord('m') or key == ord('M'):
            arrow_mode = "image" if arrow_mode == "roi" else "roi"
            print("Arrow mode =", arrow_mode)

        if key in (KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN):
            if arrow_mode == "roi":
                if key == KEY_LEFT:
                    box_x = max(box_x - step, 0)
                elif key == KEY_RIGHT:
                    box_x = min(box_x + step, image.shape[1] - box_width)
                elif key == KEY_UP:
                    box_y = max(box_y - step, 0)
                elif key == KEY_DOWN:
                    box_y = min(box_y + step, image.shape[0] - box_height)

                center_view_on_roi()
                


            else:  
                dx = dy = 0
                if key == KEY_LEFT:  dx = step
                if key == KEY_RIGHT: dx = -step
                if key == KEY_UP:    dy = step
                if key == KEY_DOWN:  dy = -step

                max_left = 0
                max_top = 0
                min_left = -(image.shape[1] * scale - display_width)
                min_top  = -(image.shape[0] * scale - display_height)
                if min_left > 0: min_left = 0
                if min_top > 0:  min_top = 0

                offset_x = int(np.clip(offset_x + dx, min_left, max_left))
                offset_y = int(np.clip(offset_y + dy, min_top, max_top))

        
        

        if key == ord('{'):
            new_height = box_height - 5
            if new_height >= min_box_size:
                box_height = new_height
        if key == ord('u') or key==ord('U'):  
         inset_margin_height = min(inset_margin_height + 1, box_height // 2)
        elif key == ord('j') or key== ord('J'):  
          inset_margin_height = max(inset_margin_height - 1, 0)
                
        elif key == ord('i') or key== ord('I'):  
            inset_margin_width = min(inset_margin_width + 1, box_width // 2)

        elif key == ord('k') or key==ord('K'):  
            inset_margin_width = max(inset_margin_width - 1, 0)

        elif key == ord('p') or key== ord('P'):  
            if final_results:
                bx0 = frozen_box_x if frozen_box_x is not None else box_x
                by0 = frozen_box_y if frozen_box_y is not None else box_y

                save_results_to_csv(final_results, bx0, by0,
                    inset_margin_width=inset_margin_width,
                    inset_margin_height=inset_margin_height)



        if key == ord('a'):
            box_x = max(box_x - box_speed, 0)
        elif key == ord('d'):
             box_x = min(box_x + box_speed, image.shape[1] - box_width)
        elif key == ord('w'):
            box_y = max(box_y - box_speed, 0)
        elif key == ord('s'):
            box_y = min(box_y + box_speed, image.shape[0] - box_height)
        elif key == ord('r'): 
          box_x, box_y = 60, 60
          box_width, box_height = 100, 100

        if key == 13 or key == 32:
            roi_gray = gray[box_y:box_y + box_height, box_x:box_x + box_width]
            final_results = find_white_in_black_shapes(roi_gray)

            
            
            frozen_box_x, frozen_box_y = box_x, box_y

            show_stats_popup(final_results, frozen_box_x, frozen_box_y,
                 highlight_inset=highlight_inset,
                 inset_margin_width=inset_margin_width,
                 inset_margin_height=inset_margin_height)

        
        elif key == 9:  
            if final_results:
                bx0 = frozen_box_x if frozen_box_x is not None else box_x
                by0 = frozen_box_y if frozen_box_y is not None else box_y

                show_chip_statistics(final_results, bx0, by0,
                     highlight_inset=highlight_inset,
                     inset_margin_width=inset_margin_width,
                     inset_margin_height=inset_margin_height)
            
        elif key == 27:  
            break

    cv2.destroyAllWindows()

def browse_file(file_label, preview_canvas):
    global selected_file_path
    file_path = filedialog.askopenfilename(
        title="Select a CSAM image file",
        filetypes=[("Image Files", "*.jpeg *.jpg *.png")]
    )
    if not file_path:
        return

    selected_file_path = file_path
    file_label.config(text=file_path)

    img = Image.open(file_path)
    photo = ImageTk.PhotoImage(img)

    
    preview_canvas.delete("all")
    preview_canvas.create_image(0, 0, image=photo, anchor="nw")

    
    preview_canvas.image = photo

    
    preview_canvas.config(scrollregion=(0, 0, photo.width(), photo.height()))

def main():
    root = tk.Tk()
    global tk_root
    tk_root = root

    
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    w = int(sw * 0.85)
    h = int(sh * 0.85)
    x = int((sw - w) / 2)
    y = int((sh - h) / 2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    root.configure(bg="#EAE3C3")
    root.title("C2W CSAM Void Analyzer")
    poll_ui_queue()

    
    root.grid_rowconfigure(1, weight=1)   
    root.grid_columnconfigure(0, weight=1)

    top = tk.Frame(root, bg="#EAE3C3")
    top.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
    top.grid_columnconfigure(0, weight=1)

    tk.Label(top, text="Please input the CSAM image file below:", bg="#EAE3C3").grid(
        row=0, column=0, sticky="w"
    )

    file_label = tk.Label(top, text="No file selected", bg="#EAE3C3", anchor="w")
    file_label.grid(row=1, column=0, sticky="ew", pady=(6, 0))

    browse_button = tk.Button(
        top, text="Browse",
        command=lambda: browse_file(file_label, preview_canvas)  
    )
    browse_button.grid(row=1, column=1, sticky="e", padx=(10, 0), pady=(6, 0))

    
    thr_frame = tk.Frame(top, bg="#EAE3C3")
    thr_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))

    tk.Label(thr_frame, text="Highlight threshold (%):", bg="#EAE3C3").pack(side="left")

    thr_var = tk.StringVar(value=str(threshold_pct))
    thr_entry = tk.Entry(thr_frame, textvariable=thr_var, width=8)
    thr_entry.pack(side="left", padx=(8, 6))


    status_var = tk.StringVar(value="✎ Edit")
    status_label = tk.Label(
        thr_frame,
        textvariable=status_var,
        bg="#EAE3C3",
        fg="gray"
    )
    status_label.pack(side="left", padx=(6, 6))

    def apply_threshold():
        global threshold_pct
        try:
            threshold_pct = float(thr_var.get())
            status_var.set("✔ Applied")
            status_label.config(fg="green")
        except ValueError:
            threshold_pct = 10.0
            thr_var.set("10.0")
            status_var.set("⚠ Invalid")
            status_label.config(fg="red")

    tk.Button(thr_frame, text="Apply", command=apply_threshold).pack(side="left")

 
    def on_threshold_edit(*args):
        status_var.set("✎ Edit")
        status_label.config(fg="gray")

    thr_var.trace_add("write", on_threshold_edit)


    
    mid = tk.Frame(root, bg="#EAE3C3")
    mid.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
    mid.grid_rowconfigure(0, weight=1)
    mid.grid_columnconfigure(0, weight=1)

    preview_canvas = tk.Canvas(mid, bg="#EAE3C3", highlightthickness=0)
    preview_canvas.grid(row=0, column=0, sticky="nsew")

    vbar = tk.Scrollbar(mid, orient="vertical", command=preview_canvas.yview)
    vbar.grid(row=0, column=1, sticky="ns")
    hbar = tk.Scrollbar(mid, orient="horizontal", command=preview_canvas.xview)
    hbar.grid(row=1, column=0, sticky="ew")

    preview_canvas.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)

    
    def _on_mousewheel(event):
        preview_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    preview_canvas.bind_all("<MouseWheel>", _on_mousewheel)

    
    bottom = tk.Frame(root, bg="#EAE3C3")
    bottom.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
    bottom.grid_columnconfigure(0, weight=1)

    def start_analysis():
        global analysis_running, analysis_thread
        if analysis_running:
            return  

        analysis_running = True
        run_button.config(state="disabled")  

        def _runner():
            global analysis_running
            try:
                main1()
            finally:
                analysis_running = False
                try:
                    run_button.config(state="normal")
                except Exception:
                    pass

        analysis_thread = threading.Thread(target=_runner, daemon=True)
        analysis_thread.start()

    run_button = tk.Button(bottom, text="Analyze", command=start_analysis)
    run_button.grid(row=0, column=0, sticky="e")

    root.mainloop()

    


if __name__ == "__main__":
    main()