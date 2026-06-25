# import tkinter as tk
# import threading
# import speech_recognition as sr
# import pyttsx3
# import numpy as np
# import time

# class SmartCaneApp:
#     def __init__(self, root):
#         self.root = root
#         self.root.title("Smart Cane LiDAR & Voice Prototype")
#         self.root.geometry("650x550")
#         self.root.configure(bg="#0a0e1a")

#         # --- 1. Simulator State Variables ---
#         self.nearest_obstacle = "Wall"
#         self.distance = 1.2  # meters
#         self.direction = "ahead-left"
#         self.current_volume = 0 # For the sound bar

#         # --- 2. Voice Engines ---
#         self.engine = pyttsx3.init()
#         self.recognizer = sr.Recognizer()
#         # Sensitivity: Lower = more sensitive to quiet voices
#         self.recognizer.energy_threshold = 300 
#         self.recognizer.dynamic_energy_threshold = True

#         # --- 3. UI Elements ---
#         self.canvas = tk.Canvas(root, width=600, height=350, bg="#111827", highlightthickness=0)
#         self.canvas.pack(pady=20)

#         # Visual Sound Bar
#         self.canvas.create_text(60, 310, text="MIC INPUT", fill="#9CA3AF", font=("Arial", 9, "bold"))
#         self.volume_bar = self.canvas.create_rectangle(30, 300, 30, 320, fill="#10B981", outline="")
        
#         # Status Text on Canvas
#         self.info_text = self.canvas.create_text(300, 150, text="Lidar Active\nWaiting for Voice...", 
#                                                fill="white", font=("Arial", 14), justify="center")

#         self.label = tk.Label(root, text="Press 'V' to speak", fg="#9CA3AF", bg="#0a0e1a", font=("Arial", 10))
#         self.label.pack()

#         self.btn = tk.Button(root, text="Listen (V)", command=self.start_voice_thread, 
#                              bg="#3B82F6", fg="white", font=("Arial", 12, "bold"), padx=20)
#         self.btn.pack(pady=10)

#         # Bindings
#         self.root.bind('<v>', lambda e: self.start_voice_thread())
        
#         # Start the UI Refresh Loop
#         self.update_ui_loop()
#         self.recognizer.energy_threshold = 50

#     # --- Voice Logic ---
#     def speak(self, text):
#         """Speaks text without locking the UI."""
#         print(f"Cane: {text}")
#         self.engine.say(text)
#         self.engine.runAndWait()

#     def start_voice_thread(self):
#         """Triggers the ear in the background."""
#         threading.Thread(target=self.listen_and_respond, daemon=True).start()

#     def listen_and_respond(self):
#         # Uses Default Mic (NVIDIA Broadcast as per your screenshot)
#         with sr.Microphone() as source:
#             self.canvas.itemconfig(self.info_text, text="Listening...", fill="#3B82F6")
#             print("Listening...")
            
#             # Calibrate for NVIDIA Broadcast noise floor
#             self.recognizer.adjust_for_ambient_noise(source, duration=0.6)
            
#             try:
#                 # Listen for up to 5 seconds
#                 audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=8)
                
#                 # Update Volume Bar briefly based on captured audio
#                 raw_data = np.frombuffer(audio.get_raw_data(), dtype=np.int16)
#                 self.current_volume = np.abs(raw_data).mean() / 50 
                
#                 self.canvas.itemconfig(self.info_text, text="Processing...", fill="#F59E0B")
#                 command = self.recognizer.recognize_google(audio).lower()
#                 print(f"User said: {command}")
                
#                 self.process_command(command)
                
#             except sr.WaitTimeoutError:
#                 self.speak("I didn't hear anything.")
#             except sr.UnknownValueError:
#                 self.speak("I couldn't understand that.")
#             except Exception as e:
#                 print(f"Error: {e}")
            
#             # Reset UI
#             self.current_volume = 0
#             self.canvas.itemconfig(self.info_text, text="Lidar Active\nReady", fill="white")

#     def process_command(self, command):
#         """The brain of the cane."""
#         # Check for Status Keywords
#         if any(word in command for word in ["status", "report", "see", "look", "around"]):
#             response = f"I detect a {self.nearest_obstacle} about {self.distance} meters to your {self.direction}."
            
#         # Check for Safety Keywords
#         elif any(word in command for word in ["safe", "clear", "go", "walk", "move"]):
#             if self.distance < 0.8:
#                 response = f"Stop. The {self.nearest_obstacle} is too close for safety."
#             else:
#                 response = "The path ahead is clear for one meter."

#         # Help
#         elif "help" in command:
#             response = "Ask me for a status report or if it is safe to walk."
            
#         else:
#             response = f"I heard {command}, but I don't know that command."
        
#         self.speak(response)

#     # --- UI Refresh Logic ---
#     def update_ui_loop(self):
#         """Continuously updates the sound bar and animations."""
#         # Sound bar width logic (max 200px)
#         target_width = min(self.current_volume * 2, 250)
#         current_coords = self.canvas.coords(self.volume_bar)
        
#         # Smoothly animate the bar returning to zero
#         new_width = 30 + target_width
#         self.canvas.coords(self.volume_bar, 30, 300, new_width, 320)
        
#         # Color transition: Green to Red
#         color = "#10B981" if target_width < 150 else "#EF4444"
#         self.canvas.itemconfig(self.volume_bar, fill=color)

#         # Decay volume slowly if not listening
#         if self.current_volume > 0:
#             self.current_volume *= 0.8
            
#         self.root.after(50, self.update_ui_loop)

# if __name__ == "__main__":
#     root = tk.Tk()
#     app = SmartCaneApp(root)
#     root.mainloop()
import tkinter as tk
from tkinter import ttk
import math

# ── Constants (From your original code) ──────────────────────────────────────
W, H       = 700, 560
SCALE      = 70
DARK_BG    = "#0a0e1a"
RAY_CLEAR  = "#4FC3F7" # Removed hex alpha as standard Tkinter doesn't support it
RAY_HIT    = "#FF7043"
PERSON_CLR = "#FFD54F"

PRESET_OBSTACLES = [
    {"type": "rect",   "x": 180, "y": 130, "w": 90,  "h": 18, "color": "#D84315", "label": "Wall"},
    {"type": "rect",   "x": 380, "y": 130, "w": 90,  "h": 18, "color": "#D84315", "label": "Wall"},
    {"type": "rect",   "x": 120, "y": 130, "w": 18,  "h": 200,"color": "#D84315", "label": "Wall"},
    {"type": "rect",   "x": 422, "y": 130, "w": 18,  "h": 200,"color": "#D84315", "label": "Wall"},
    {"type": "circle", "x": 280, "y": 260, "r": 22,             "color": "#5C6BC0", "label": "Pillar"},
    {"type": "rect",   "x": 200, "y": 360, "w": 60,  "h": 30, "color": "#FF7043", "label": "Bench"},
    {"type": "circle", "x": 380, "y": 340, "r": 16,             "color": "#26A69A", "label": "Bin"},
]

# ── Geometry helpers (Your Logic) ───────────────────────────────────────────

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

# ── Main Application ───────────────────────────────────────────────────────

class LidarSim:
    def __init__(self, root):
        self.root = root
        self.root.title("LiDAR Obstacle Detection Sim")
        
        self.canvas = tk.Canvas(root, width=W, height=H, bg=DARK_BG, highlightthickness=0)
        self.canvas.pack()
        
        self.px, self.py = W//2, H//2  # Initial person position
        self.num_rays = 36             # Number of LiDAR rays
        
        self.canvas.bind("<Motion>", self.update_position)
        self.render()

    def update_position(self, event):
        self.px, self.py = event.x, event.y
        self.render()

    def render(self):
        self.canvas.delete("all")
        
        # Draw Obstacles
        for obs in PRESET_OBSTACLES:
            if obs["type"] == "rect":
                self.canvas.create_rectangle(obs["x"], obs["y"], obs["x"]+obs["w"], 
                                            obs["y"]+obs["h"], fill=obs["color"], outline="")
            elif obs["type"] == "circle":
                self.canvas.create_oval(obs["x"]-obs["r"], obs["y"]-obs["r"], 
                                       obs["x"]+obs["r"], obs["y"]+obs["r"], fill=obs["color"], outline="")

        # Cast Rays
        for i in range(self.num_rays):
            angle = (i / self.num_rays) * 2 * math.pi
            dx, dy = math.cos(angle), math.sin(angle)
            
            closest_t = 1000 # Max ray distance
            hit = False

            for obs in PRESET_OBSTACLES:
                t = None
                if obs["type"] == "rect":
                    # Check all 4 sides of rectangle
                    x, y, w, h = obs["x"], obs["y"], obs["w"], obs["h"]
                    sides = [(x,y,x+w,y), (x+w,y,x+w,y+h), (x+w,y+h,x,y+h), (x,y+h,x,y)]
                    for s in sides:
                        res = seg_intersect(self.px, self.py, dx, dy, *s)
                        if res and res < closest_t: closest_t = res; hit = True
                elif obs["type"] == "circle":
                    res = circle_ray_intersect(self.px, self.py, dx, dy, obs["x"], obs["y"], obs["r"])
                    if res and res < closest_t: closest_t = res; hit = True

            # Draw Ray
            end_x = self.px + dx * closest_t
            end_y = self.py + dy * closest_t
            color = RAY_HIT if hit and closest_t < 150 else RAY_CLEAR
            self.canvas.create_line(self.px, self.py, end_x, end_y, fill=color, dash=(2, 2) if not hit else None)

        # Draw Person
        self.canvas.create_oval(self.px-8, self.py-8, self.px+8, self.py+8, fill=PERSON_CLR)

if __name__ == "__main__":
    root = tk.Tk()
    app = LidarSim(root)
    root.mainloop()