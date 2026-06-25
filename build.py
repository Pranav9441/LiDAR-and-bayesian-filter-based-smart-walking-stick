import tkinter as tk
import threading
import speech_recognition as sr
import pyttsx3
import numpy as np
import math
import time

# ── Constants ──
W, H        = 700, 560
SCALE       = 70
DARK_BG     = "#0a0e1a"
RAY_CLEAR   = "#4FC3F7"
RAY_HIT     = "#EF5350"
PERSON_CLR  = "#FFD54F"

PRESET_OBSTACLES = [
    {"type": "rect",   "x": 180, "y": 130, "w": 90,  "h": 18, "color": "#D84315", "label": "Wall"},
    {"type": "rect",   "x": 380, "y": 130, "w": 90,  "h": 18, "color": "#D84315", "label": "Wall"},
    {"type": "rect",   "x": 120, "y": 130, "w": 18,  "h": 200,"color": "#D84315", "label": "Wall"},
    {"type": "rect",   "x": 422, "y": 130, "w": 18,  "h": 200,"color": "#D84315", "label": "Wall"},
    {"type": "circle", "x": 280, "y": 260, "r": 22,             "color": "#5C6BC0", "label": "Pillar"},
    {"type": "rect",   "x": 200, "y": 360, "w": 60,  "h": 30, "color": "#FF7043", "label": "Bench"},
    {"type": "circle", "x": 380, "y": 340, "r": 16,             "color": "#26A69A", "label": "Bin"},
]

# ── Geometry Helpers ──
def seg_intersect(px, py, dx, dy, ax, ay, bx, by):
    denom = dx * (by - ay) - dy * (bx - ax)
    if abs(denom) < 1e-10: return None
    t = ((ax - px) * (by - ay) - (ay - py) * (bx - ax)) / denom
    u = ((ax - px) * dy - (ay - py) * dx) / denom
    if t >= 0 and 0 <= u <= 1: return t
    return None

def circle_ray_intersect(px, py, dx, dy, cx, cy, r):
    fx, fy = px - cx, py - cy
    a = dx * dx + dy * dy
    b = 2 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - r * r
    disc = b * b - 4 * a * c
    if disc < 0: return None
    sq = math.sqrt(disc)
    t1 = (-b - sq) / (2 * a)
    t2 = (-b + sq) / (2 * a)
    return t1 if t1 >= 0 else (t2 if t2 >= 0 else None)

class SmartCaneIntegrated:
    def __init__(self, root):
        self.root = root
        self.root.title("Integrated Smart Cane LiDAR & Voice")
        self.root.configure(bg=DARK_BG)

        # 1. State Variables
        self.px, self.py = W//2, H//2  # Mouse-controlled position
        self.num_rays = 36
        self.current_volume = 0
        
        # This dictionary stores the result of the LATEST Lidar scan
        self.live_scan = {
            "dist": 1000,
            "label": "Nothing",
            "dir": "ahead"
        }

        # 2. Voice Engines
        self.engine = pyttsx3.init()
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 50 # Sensitivity fix

        # 3. UI Elements
        self.canvas = tk.Canvas(root, width=W, height=H, bg=DARK_BG, highlightthickness=0)
        self.canvas.pack()

        # Voice Status Text (Overlaid on Canvas)
        self.info_text = self.canvas.create_text(W//2, 50, text="Hold Mouse to Scan | Press 'V' to Talk", 
                                               fill="white", font=("Arial", 12))
        self.volume_bar = self.canvas.create_rectangle(10, H-30, 10, H-10, fill="#10B981", outline="")

        # Bindings
        self.canvas.bind("<Motion>", self.update_lidar)
        self.root.bind('<v>', lambda e: self.start_voice_thread())
        
        # Start UI loop for animations
        self.update_ui_loop()

    def update_lidar(self, event):
        """Standard Lidar render logic merged with 'Live Scan' detection."""
        self.px, self.py = event.x, event.y
        self.render_lidar()

    def render_lidar(self):
        self.canvas.delete("ray")
        self.canvas.delete("person")
        self.canvas.delete("obs")

        # Draw Obstacles (static)
        for obs in PRESET_OBSTACLES:
            if obs["type"] == "rect":
                self.canvas.create_rectangle(obs["x"], obs["y"], obs["x"]+obs["w"], 
                                           obs["y"]+obs["h"], fill=obs["color"], outline="", tags="obs")
            elif obs["type"] == "circle":
                self.canvas.create_oval(obs["x"]-obs["r"], obs["y"]-obs["r"], 
                                       obs["x"]+obs["r"], obs["y"]+obs["r"], fill=obs["color"], outline="", tags="obs")

        # Reset nearest scan for this frame
        nearest_t = 1000
        nearest_label = "Clear Path"

        # Cast Rays
        for i in range(self.num_rays):
            angle = (i / self.num_rays) * 2 * math.pi
            dx, dy = math.cos(angle), math.sin(angle)
            
            ray_t = 1000
            ray_label = ""

            for obs in PRESET_OBSTACLES:
                t = None
                if obs["type"] == "rect":
                    x, y, w, h = obs["x"], obs["y"], obs["w"], obs["h"]
                    sides = [(x,y,x+w,y), (x+w,y,x+w,y+h), (x+w,y+h,x,y+h), (x,y+h,x,y)]
                    for s in sides:
                        res = seg_intersect(self.px, self.py, dx, dy, *s)
                        if res and res < ray_t: 
                            ray_t = res
                            ray_label = obs["label"]
                elif obs["type"] == "circle":
                    res = circle_ray_intersect(self.px, self.py, dx, dy, obs["x"], obs["y"], obs["r"])
                    if res and res < ray_t: 
                        ray_t = res
                        ray_label = obs["label"]

            # Store absolute nearest for voice brain
            if ray_t < nearest_t:
                nearest_t = ray_t
                nearest_label = ray_label

            # Draw
            end_x = self.px + dx * ray_t
            end_y = self.py + dy * ray_t
            color = RAY_HIT if ray_t < 150 else RAY_CLEAR
            self.canvas.create_line(self.px, self.py, end_x, end_y, fill=color, tags="ray")

        # Update Live Scan State (scaled to 'meters')
        self.live_scan["dist"] = nearest_t / SCALE
        self.live_scan["label"] = nearest_label
        
        # Draw Person
        self.canvas.create_oval(self.px-8, self.py-8, self.px+8, self.py+8, fill=PERSON_CLR, tags="person")

    # --- Voice Logic ---
    def speak(self, text):
        self.engine.say(text)
        self.engine.runAndWait()

    def start_voice_thread(self):
        threading.Thread(target=self.listen_and_respond, daemon=True).start()

    def listen_and_respond(self):
        with sr.Microphone() as source:
            self.canvas.itemconfig(self.info_text, text="Listening...", fill="#3B82F6")
            self.recognizer.adjust_for_ambient_noise(source, duration=0.6)
            try:
                audio = self.recognizer.listen(source, timeout=4, phrase_time_limit=5)
                # Update sound bar
                raw_data = np.frombuffer(audio.get_raw_data(), dtype=np.int16)
                self.current_volume = np.abs(raw_data).mean() / 40
                
                command = self.recognizer.recognize_google(audio).lower()
                self.process_command(command)
            except:
                self.speak("I couldn't hear you clearly.")
            
            self.current_volume = 0
            self.canvas.itemconfig(self.info_text, text="Hold Mouse to Scan | Press 'V' to Talk", fill="white")

    def process_command(self, command):
        dist = self.live_scan["dist"]
        label = self.live_scan["label"]

        if any(word in command for word in ["status", "report", "see", "mi"]):
            if dist > 4:
                response = "The path ahead is clear for over four meters."
            else:
                response = f"I detect a {label} about {dist:.1f} meters away."
        elif any(word in command for word in ["safe", "clear", "go"]):
            response = "It is safe." if dist > 0.8 else f"Stop. {label} is too close."
        else:
            response = f"I heard {command}. Try asking for a status report."
        
        self.speak(response)

    def update_ui_loop(self):
        # Update sound bar visual
        vol_width = min(self.current_volume * 2, 300)
        self.canvas.coords(self.volume_bar, 10, H-30, 10 + vol_width, H-10)
        if self.current_volume > 0: self.current_volume *= 0.8
        self.root.after(50, self.update_ui_loop)

if __name__ == "__main__":
    root = tk.Tk()
    app = SmartCaneIntegrated(root)
    root.mainloop()