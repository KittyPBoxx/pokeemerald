import tkinter as tk
from tkinter import filedialog, ttk
from PIL import Image, ImageTk
import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.ndimage import distance_transform_edt
import math

USE_BLUR = True
USE_HEIGHT_CURVE = True
USE_OUTLINE_BOOST = True

BLUR_SIGMA = 0.5
GAMMA = 1.5
OUTLINE_THRESHOLD = 0.1
SOBEL_STRENGTH = 3.0
HEIGHT_MODE = "Lightness"
SCALE_IMAGE = 4

PALETTE_BASE = [
    [0,0,0], [141,135,252], [55,229,151], [166,253,169], [255,227,121],
    [15,127,159], [253,127,150], [44,26,162], [135,10,157], [215,41,153],
    [80,188,225], [193,183,221], [53,130,233], [201,124,231], [66,49,206],
    [185,55,218]
]

def generate_normal_map(img_path, blur=BLUR_SIGMA, gamma=GAMMA, outline=OUTLINE_THRESHOLD,
                        strength=SOBEL_STRENGTH, use_blur=USE_BLUR, use_curve=USE_HEIGHT_CURVE,
                        use_outline=USE_OUTLINE_BOOST, height_mode=HEIGHT_MODE):
    img = Image.open(img_path).convert("RGBA")
    data = np.asarray(img).astype(np.float32) / 255.0
    h, w, _ = data.shape

    tl_pixel = data[0,0,:3].copy()
    PALETTE_BASE[0] = (tl_pixel*255).astype(int).tolist()
    background_mask = np.all(np.isclose(data[...,:3], tl_pixel, atol=1/255), axis=2)

    if height_mode == "Lightness":
        height = (np.max(data[...,:3], axis=2) + np.min(data[...,:3], axis=2)) / 2
    elif height_mode == "Value":
        height = np.max(data[...,:3], axis=2)
    elif height_mode == "Distance":
        mask = np.any(data[...,:3] > 0.01, axis=2)
        height = distance_transform_edt(mask) / max(h, w)
        height = 1.0 - height

    height[background_mask] = 0.0

    if use_blur:
        height = gaussian_filter(height, sigma=blur)
    if use_curve:
        height = np.clip(height**gamma, 0, 1)
    if use_outline:
        mask = height < outline
        height[mask] *= 0.25

    sobel_x = np.array([[-1,0,1],[-2,0,2],[-1,0,1]], np.float32)
    sobel_y = np.array([[-1,-2,-1],[0,0,0],[1,2,1]], np.float32)

    def convolve(img, kernel):
        kh, kw = kernel.shape
        pad_y, pad_x = kh//2, kw//2
        padded = np.pad(img, ((pad_y,pad_y),(pad_x,pad_x)), mode='edge')
        out = np.zeros_like(img)
        for y in range(h):
            for x in range(w):
                out[y,x] = np.sum(padded[y:y+kh, x:x+kw]*kernel)
        return out

    dx = convolve(height, sobel_x) * strength
    dy = convolve(height, sobel_y) * strength
    dy = -dy

    nx = -dx
    ny = -dy
    nz = np.ones_like(nx)
    length = np.sqrt(nx**2 + ny**2 + nz**2)
    nx /= length
    ny /= length
    nz /= length

    normal_rgb = np.stack([(nx*0.5+0.5),(ny*0.5+0.5),(nz*0.5+0.5)], axis=-1)

    palette_array = []
    for i, c in enumerate(PALETTE_BASE):
        if i == 0: continue
        vec = np.array(c)/255.0*2 - 1
        n = np.linalg.norm(vec)
        if n == 0:
            vec = np.array([0.0,0.0,1.0])
        else:
            vec /= n
        palette_array.append(vec*0.5 + 0.5)
    palette_array = np.array(palette_array)

    flat_normals = normal_rgb.reshape(-1,3)
    distances = np.sqrt(((flat_normals[:,None,:] - palette_array[None,:,:])**2).sum(axis=2))
    indices = np.argmin(distances, axis=1) + 1
    indexed = indices.reshape(h,w)
    indexed[background_mask] = 0

    out_img = Image.fromarray(indexed.astype(np.uint8))
    flat_palette = [v for color in PALETTE_BASE for v in color] + [0]*(256*3 - len(PALETTE_BASE)*3)
    out_img.putpalette(flat_palette)
    return out_img

def decode_indexed_normal_to_vectors_and_mask(p_img):
    palette = p_img.getpalette()
    pal = np.array(palette, dtype=np.uint8).reshape(-1, 3)
    idx_arr = np.array(p_img, dtype=np.uint8)
    h, w = idx_arr.shape
    flat_rgb = pal[idx_arr.flatten()]
    flat_rgb_f = flat_rgb.astype(np.float32) / 255.0
    vecs = (flat_rgb_f - 0.5) * 2.0
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    zero_mask = (norms.squeeze() == 0)
    valid = norms.squeeze() > 0
    vecs[valid] /= norms[valid]
    vecs[zero_mask] = np.array([0.0, 0.0, 1.0])
    normals = vecs.reshape((h, w, 3)).astype(np.float32)
    bg_mask = (idx_arr == 0)
    return normals, bg_mask

def shade_with_directional_light_blend(orig_rgb_image, normal_vectors, bg_mask, angle_deg, light_color_rgb, ambient=0.12):
    az = math.radians(angle_deg)
    elev = math.radians(60.0)
    lx = math.cos(elev) * math.cos(az)
    ly = math.cos(elev) * math.sin(az)
    lz = math.sin(elev)
    L = np.array([lx, ly, lz], dtype=np.float32)
    L /= np.linalg.norm(L)

    orig = np.asarray(orig_rgb_image.convert("RGB")).astype(np.float32) / 255.0
    N = normal_vectors
    dot = (N * L[None, None, :]).sum(axis=2)
    diffuse = np.clip(dot, 0.0, 1.0)[:, :, None]
    light_color = np.array(light_color_rgb, dtype=np.float32)[None, None, :]
    shaded = orig * (ambient + diffuse * light_color)
    final = 0.5 * orig + 0.5 * shaded
    final = np.clip(final, 0.0, 1.0)
    final_u8 = (final * 255.0).astype(np.uint8)
    final_u8[bg_mask, :] = np.asarray(orig_rgb_image.convert("RGB"))[bg_mask, :]
    return Image.fromarray(final_u8)

class NormalMapApp:
    def __init__(self, root):
        self.root = root
        root.title("Normal Map Maker")
        self.img_path = None
        self.orig_image = None
        self.current_normal = None
        self.preview_normal_img = None
        self.preview_lit_img = None
    
        row1 = tk.Frame(root)
        row1.pack(side="top", fill="x", pady=4, padx=4)
        tk.Button(row1, text="Open", command=self.load_image).pack(side="left", padx=3)
        tk.Button(row1, text="Import Normal", command=self.import_normal).pack(side="left", padx=3)
        tk.Button(row1, text="Export Normal", command=self.export_png).pack(side="left", padx=3)
        tk.Button(row1, text="Export Stitch", command=self.export_stitch).pack(side="left", padx=3)
        tk.Button(row1, text="Reset", command=self.reset_settings).pack(side="left", padx=3)
        tk.Label(row1, text="Scale").pack(side="left", padx=6)
        self.scale_var = tk.IntVar(value=SCALE_IMAGE)
        self.scale_combo = ttk.Combobox(row1, textvariable=self.scale_var,
                                        values=[1,2,3,4,5,6,7,8], width=3)
        self.scale_combo.pack(side="left")
        self.scale_combo.bind("<<ComboboxSelected>>", lambda e: self.update_preview())

        row2 = tk.Frame(root)
        row2.pack(side="top", fill="x", padx=6, pady=2)
        tk.Label(row2, text="Blur").pack(anchor="w")
        slider_row = tk.Frame(row2)
        slider_row.pack(fill="x")
        self.blur_scale = tk.Scale(slider_row, from_=0, to=5, resolution=0.01,
                                   orient="horizontal", command=lambda e: self.regenerate_normal())
        self.blur_scale.set(BLUR_SIGMA)
        self.blur_scale.pack(side="left", fill="x", expand=True)
        self.bl_var = tk.BooleanVar(value=USE_BLUR)
        tk.Checkbutton(slider_row, text="Enable", variable=self.bl_var,
                       command=self.regenerate_normal).pack(side="left", padx=6)

        row3 = tk.Frame(root)
        row3.pack(side="top", fill="x", padx=6, pady=2)
        tk.Label(row3, text="Gamma").pack(anchor="w")
        slider_row = tk.Frame(row3)
        slider_row.pack(fill="x")
        self.gamma_scale = tk.Scale(slider_row, from_=0.1, to=5, resolution=0.01,
                                    orient="horizontal", command=lambda e: self.regenerate_normal())
        self.gamma_scale.set(GAMMA)
        self.gamma_scale.pack(side="left", fill="x", expand=True)
        self.curve_var = tk.BooleanVar(value=USE_HEIGHT_CURVE)
        tk.Checkbutton(slider_row, text="Enable", variable=self.curve_var,
                       command=self.regenerate_normal).pack(side="left", padx=6)

        row4 = tk.Frame(root)
        row4.pack(side="top", fill="x", padx=6, pady=2)
        tk.Label(row4, text="Outline Threshold").pack(anchor="w")
        slider_row = tk.Frame(row4)
        slider_row.pack(fill="x")
        self.outline_scale = tk.Scale(slider_row, from_=0, to=1, resolution=0.01,
                                      orient="horizontal", command=lambda e: self.regenerate_normal())
        self.outline_scale.set(OUTLINE_THRESHOLD)
        self.outline_scale.pack(side="left", fill="x", expand=True)
        self.outline_var = tk.BooleanVar(value=USE_OUTLINE_BOOST)
        tk.Checkbutton(slider_row, text="Enable", variable=self.outline_var,
                       command=self.regenerate_normal).pack(side="left", padx=6)

        row5 = tk.Frame(root)
        row5.pack(side="top", fill="x", padx=6, pady=2)
        tk.Label(row5, text="Strength").pack(anchor="w")
        self.strength_scale = tk.Scale(row5, from_=0, to=10, resolution=0.1,
                                       orient="horizontal", command=lambda e: self.regenerate_normal())
        self.strength_scale.set(SOBEL_STRENGTH)
        self.strength_scale.pack(fill="x", pady=2)

        tk.Label(root, text="Height Mode").pack(anchor="w")
        self.mode_combo = ttk.Combobox(root, values=["Lightness", "Value", "Distance"])
        self.mode_combo.set(HEIGHT_MODE)
        self.mode_combo.pack(fill="x", pady=2)
        self.mode_combo.bind("<<ComboboxSelected>>", lambda e: self.regenerate_normal())

        row6 = tk.Frame(root)
        row6.pack(side="top", fill="both", expand=False, padx=6, pady=6)
        self.normal_preview_label = tk.Label(row6)
        self.normal_preview_label.pack(side="left", padx=4)

        row7 = tk.Frame(root)
        row7.pack(side="top", fill="x", padx=6, pady=2)
        angle_frame = tk.Frame(row7)
        angle_frame.pack(side="left", fill="x", expand=True, padx=4)
        tk.Label(angle_frame, text="Angle").pack(anchor="w")
        self.angle_scale = tk.Scale(angle_frame, from_=0, to=360, resolution=1,
                                    orient="horizontal", command=lambda e: self.update_preview())
        self.angle_scale.set(45)
        self.angle_scale.pack(fill="x")
        color_frame = tk.Frame(row7)
        color_frame.pack(side="right", padx=4)
        tk.Label(color_frame, text="Light Color").pack(anchor="w")
        self.light_color_var = tk.StringVar(value="White")
        self.light_color_combo = ttk.Combobox(color_frame, textvariable=self.light_color_var,
                                              values=["White","Orange","Yellow","Red","Green","Blue","Purple"], width=10)
        self.light_color_combo.pack()
        self.light_color_combo.bind("<<ComboboxSelected>>", lambda e: self.update_preview())

        row8 = tk.Frame(root)
        row8.pack(side="top", fill="both", expand=False, padx=6, pady=6)
        self.lit_preview_label = tk.Label(row8)
        self.lit_preview_label.pack(side="left", padx=4)

        self.clear_previews()

    def clear_previews(self):
        blank = Image.new("RGBA", (128, 128), (200,200,200,255))
        self.preview_normal_img = ImageTk.PhotoImage(blank)
        self.preview_lit_img = ImageTk.PhotoImage(blank)
        self.normal_preview_label.configure(image=self.preview_normal_img)
        self.lit_preview_label.configure(image=self.preview_lit_img)

    def load_image(self):
        path = filedialog.askopenfilename(filetypes=[("Images", ("*.png","*.jpg","*.bmp"))])
        if not path:
            return
        self.img_path = path
        self.orig_image = Image.open(self.img_path).convert("RGB")
        self.current_normal = generate_normal_map(
            self.img_path,
            blur=self.blur_scale.get(),
            gamma=self.gamma_scale.get(),
            outline=self.outline_scale.get(),
            strength=self.strength_scale.get(),
            use_blur=self.bl_var.get(),
            use_curve=self.curve_var.get(),
            use_outline=self.outline_var.get(),
            height_mode=self.mode_combo.get()
        )
        self.update_preview()

    def import_normal(self):
        path = filedialog.askopenfilename(filetypes=[("PNG Normal Map","*.png")])
        if not path:
            return
        self.current_normal = Image.open(path).convert("P")
        self.update_preview()

    def regenerate_normal(self):
        if not self.img_path:
            return
        self.current_normal = generate_normal_map(
            self.img_path,
            blur=self.blur_scale.get(),
            gamma=self.gamma_scale.get(),
            outline=self.outline_scale.get(),
            strength=self.strength_scale.get(),
            use_blur=self.bl_var.get(),
            use_curve=self.curve_var.get(),
            use_outline=self.outline_var.get(),
            height_mode=self.mode_combo.get()
        )
        self.update_preview()

    def update_preview(self):
        if self.current_normal is None:
            self.clear_previews()
            return

        normal_p = self.current_normal

        scale = int(self.scale_var.get()) if self.scale_var.get() else 1
        new_size = (normal_p.width * scale, normal_p.height * scale)

        normal_preview_resized = normal_p.resize(new_size, Image.NEAREST)
        self.preview_normal_img = ImageTk.PhotoImage(normal_preview_resized.convert("RGB"))
        self.normal_preview_label.configure(image=self.preview_normal_img)

        normals_decoded, bg_mask = decode_indexed_normal_to_vectors_and_mask(normal_p)

        orig_for_shade = self.orig_image
        if (orig_for_shade.width, orig_for_shade.height) != (normal_p.width, normal_p.height):
            orig_for_shade = orig_for_shade.resize((normal_p.width, normal_p.height), Image.LANCZOS)

        color_map = {
            "White": (3.0, 3.0, 3.0),
            "Orange": (3.0, 1.8, 0.6),
            "Yellow": (3.0, 2.7, 0.6),
            "Red": (3.0, 0.6, 0.6),
            "Green": (0.6, 3.0, 0.6),
            "Blue": (0.6, 1.5, 3.0),
            "Purple": (2.4, 0.9, 3.0)
        }

        light_color_name = self.light_color_var.get() if self.light_color_var.get() else "White"
        light_color_rgb = color_map.get(light_color_name, (1.0,1.0,1.0))
        angle = float(self.angle_scale.get())

        lit_img = shade_with_directional_light_blend(orig_for_shade, normals_decoded, bg_mask, angle, light_color_rgb, ambient=0.12)
        lit_preview_resized = lit_img.resize(new_size, Image.BILINEAR)
        self.preview_lit_img = ImageTk.PhotoImage(lit_preview_resized)
        self.lit_preview_label.configure(image=self.preview_lit_img)

    def export_png(self):
        if self.current_normal is None:
            return
        path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG","*.png")])
        if path:
            self.current_normal.save(path, "PNG")

    def export_stitch(self):
        if self.current_normal is None or self.img_path is None:
            return

        orig = Image.open(self.img_path).convert("P")
        normal = self.current_normal.convert("P")
        stitched = Image.new(
            "P",
            (orig.width + normal.width, max(orig.height, normal.height))
        )
    
        stitched.putpalette(orig.getpalette())
    
        stitched.paste(orig, (0, 0))
        stitched.paste(normal, (orig.width, 0))
    
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG","*.png")]
        )
        if path:
            stitched.save(path, "PNG")


    def reset_settings(self):
        self.bl_var.set(USE_BLUR)
        self.curve_var.set(USE_HEIGHT_CURVE)
        self.outline_var.set(USE_OUTLINE_BOOST)
        self.blur_scale.set(BLUR_SIGMA)
        self.gamma_scale.set(GAMMA)
        self.outline_scale.set(OUTLINE_THRESHOLD)
        self.strength_scale.set(SOBEL_STRENGTH)
        self.mode_combo.set(HEIGHT_MODE)
        self.angle_scale.set(45)
        self.light_color_var.set("White")
        self.regenerate_normal()

root = tk.Tk()
app = NormalMapApp(root)
root.mainloop()
