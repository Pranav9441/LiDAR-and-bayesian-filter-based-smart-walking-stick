"""
Smart Walking Cane Simulator v2 — Full Integrated Application
=============================================================
Tab 1: LiDAR Scanner      — real-time obstacle detection
Tab 2: Voice / Commands   — navigation speech + typed voice commands
Tab 3: A* Route Planner   — pathfinding with animation
Tab 4: GSM Tracker        — live GPS map simulation
Tab 5: Accessibility      — settings and hardware guide

NEW: Voice Command System (Tab 2)
  Type any of these commands and press Enter or click Send:
  - "am i safe"       → checks live LiDAR, tells if you're safe or in danger
  - "status"          → full obstacle report
  - "nearest"         → closest obstacle name + distance
  - "which way"       → best direction to move
  - "stop"            → stop confirmation
  - "is path clear"   → yes/no path check
  - "where am i"      → GPS coordinates from GSM tab
  - "help"            → lists all commands

Run:  python smart_cane_v2.py
Deps: pip install pyttsx3 openai   (both optional)
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import math, random, heapq, time, threading, queue

try:
    import pyttsx3
    TTS_OK = True
except ImportError:
    TTS_OK = False

try:
    import openai
    OPENAI_OK = True
except ImportError:
    OPENAI_OK = False

# ── colours ──────────────────────────────────────────────────────────────────
DARK   = "#0a0e1a"
PANEL  = "#1a1d2e"
CARD   = "#161929"
ACCENT = "#4FC3F7"
YELLOW = "#FFD54F"
GREEN  = "#66BB6A"
RED    = "#EF5350"
ORANGE = "#FF7043"
PURPLE = "#AB47BC"
MUTED  = "#888888"
WHITE  = "#e0e0e0"
SCALE  = 70

OBS_LABELS = ["Wall","Post","Pillar","Bench","Tree","Barrier","Step","Bin","Door","Table","Chair","Railing"]
OBS_COLORS = ["#D84315","#5C6BC0","#26A69A","#AB47BC","#FF7043","#8D6E63","#EF5350","#FFA726"]

BTN       = {"fg":WHITE,"bg":"#2a2f45","font":("Courier",10),"relief":"flat","padx":10,"pady":5,"cursor":"hand2","bd":0,"activebackground":"#3a4060","activeforeground":WHITE}
BTN_GREEN = {"fg":"white","bg":"#1a4a2a","font":("Courier",10),"relief":"flat","padx":10,"pady":5,"cursor":"hand2","bd":0,"activebackground":"#2a6a3a","activeforeground":"white"}
BTN_RED   = {"fg":"white","bg":"#4a1a1a","font":("Courier",10),"relief":"flat","padx":10,"pady":5,"cursor":"hand2","bd":0,"activebackground":"#6a2a2a","activeforeground":"white"}

def card_frame(parent, **kw):
    return tk.Frame(parent, bg=CARD, **kw)

# ═══════════════════════════════════════════════════════════════════════════
#  VOICE ENGINE — runs TTS in background thread
# ═══════════════════════════════════════════════════════════════════════════
class VoiceEngine:
    def __init__(self):
        self._q = queue.Queue()
        self._engine = None
        self._active = False
        if TTS_OK:
            try:
                self._engine = pyttsx3.init()
                self._engine.setProperty('rate', 165)
                self._engine.setProperty('volume', 1.0)
                for v in self._engine.getProperty('voices'):
                    if 'english' in v.name.lower() or 'en_' in v.id.lower():
                        self._engine.setProperty('voice', v.id)
                        break
                self._active = True
                threading.Thread(target=self._worker, daemon=True).start()
            except Exception as e:
                print(f"[Voice] init error: {e}")

    def _worker(self):
        while True:
            text = self._q.get()
            if text is None: break
            try:
                self._engine.say(text)
                self._engine.runAndWait()
            except Exception:
                pass
            self._q.task_done()

    def speak(self, text, priority=False):
        if priority:
            while not self._q.empty():
                try: self._q.get_nowait()
                except: pass
        if self._active:
            self._q.put(text)
        else:
            print(f"[SPEAK] {text}")

    def stop(self):
        if self._active: self._q.put(None)


# ═══════════════════════════════════════════════════════════════════════════
#  SPEECH GENERATOR — navigation + command responses
# ═══════════════════════════════════════════════════════════════════════════
class SpeechGen:
    DANGER_T = 1.0
    NEAR_T   = 2.0
    CLEAR_MSGS = [
        "Path is clear ahead. Safe to continue.",
        "No obstacles detected. You may proceed.",
        "All clear. Continue walking forward.",
        "The way ahead is open. Safe to move.",
    ]

    COMMANDS = {
        "am i safe":"safety","safe":"safety","is it safe":"safety",
        "am i in danger":"safety","check safety":"safety",
        "status":"status","surroundings":"status","scan":"status","report":"status",
        "what is around me":"status",
        "nearest":"nearest","closest":"nearest","what is nearest":"nearest",
        "which way":"direction","where should i go":"direction",
        "which direction":"direction","best path":"direction",
        "stop":"stop","halt":"stop","freeze":"stop",
        "help":"help","commands":"help","what can i say":"help",
        "is path clear":"clear","clear ahead":"clear","path clear":"clear",
        "where am i":"location","my location":"location","location":"location",
    }

    def __init__(self, mode="rule_based", api_key=None):
        self.mode = mode
        self.api_key = api_key
        self._last = ""; self._lt = 0

    def generate(self, scan):
        dets = scan.get("detections",[])
        clear = scan.get("clear_ahead", True)
        near  = scan.get("nearest")
        if self.mode == "openai" and OPENAI_OK and self.api_key:
            return self._openai(dets, clear, near)
        return self._rules(dets, clear, near)

    def should_speak(self, text):
        now = time.time()
        if text == self._last and now - self._lt < 2.5: return False
        self._last, self._lt = text, now
        return True

    def _rules(self, dets, clear, near):
        if not dets: return random.choice(self.CLEAR_MSGS)
        dangers = [d for d in dets if d["distM"] <= self.DANGER_T]
        ahead   = [d for d in dets if "ahead" in d["dir"]]
        if dangers:
            d = dangers[0]
            return f"STOP! {d['label']} {d['dir']} — only {d['distM']:.1f} metres!"
        if not clear and ahead:
            a = ahead[0]
            sides = [d for d in dets if d["dir"] in ("left","right")]
            msg = f"Caution — {a['label']} ahead at {a['distM']:.1f} metres."
            if sides: msg += f" Also {sides[0]['label']} on your {sides[0]['dir']}."
            return msg
        if near:
            return f"Nearest: {near['label']} on your {near['dir']} at {near['distM']:.1f}m."
        return random.choice(self.CLEAR_MSGS)

    def _openai(self, dets, clear, near):
        obs = "; ".join(f"{d['label']} {d['distM']:.1f}m {d['dir']}" for d in dets[:4]) or "none"
        prompt = (f"Smart cane navigation. Obstacles: {obs}. Clear: {clear}. "
                  f"ONE instruction under 20 words. Urgent if <1m. Reply only instruction.")
        try:
            client = openai.OpenAI(api_key=self.api_key)
            r = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role":"user","content":prompt}],
                max_tokens=60, temperature=0.7)
            return r.choices[0].message.content.strip()
        except Exception:
            return self._rules(dets, clear, near)

    def handle_command(self, cmd, scan, gsm_lat=None, gsm_lon=None):
        """
        Processes a typed command against the live scan data.
        Returns the spoken/displayed response string.
        """
        cmd_lower = cmd.strip().lower()
        handler = None
        for phrase, key in self.COMMANDS.items():
            if phrase in cmd_lower:
                handler = key
                break

        dets     = scan.get("detections", [])
        clear    = scan.get("clear_ahead", True)
        near     = scan.get("nearest")
        dangers  = [d for d in dets if d["distM"] <= self.DANGER_T]
        warnings = [d for d in dets if d["distM"] <= self.NEAR_T]
        ahead    = [d for d in dets if "ahead" in d["dir"]]

        if handler == "safety":
            if dangers:
                d = dangers[0]
                return (f"YOU ARE NOT SAFE! "
                        f"{d['label']} is only {d['distM']:.1f} metres on your {d['dir']}. "
                        f"Stop moving immediately!")
            elif warnings:
                w = warnings[0]
                return (f"Caution — you are near obstacles. "
                        f"Closest is {w['label']} at {w['distM']:.1f} metres on your {w['dir']}. "
                        f"Slow down and proceed carefully.")
            else:
                return ("You are SAFE. No obstacles within 2 metres. "
                        "Path is clear. You may continue walking.")

        elif handler == "status":
            if not dets:
                return "Status: All clear. No obstacles in range. Safe to move."
            parts = [f"{d['label']} {d['distM']:.1f}m on your {d['dir']}" for d in dets[:4]]
            safety = "DANGER!" if dangers else ("Caution ahead." if not clear else "Path ahead clear.")
            return f"Status: {len(dets)} obstacles. {'; '.join(parts)}. {safety}"

        elif handler == "nearest":
            if near:
                return f"Nearest obstacle: {near['label']} on your {near['dir']} at {near['distM']:.1f} metres."
            return "No obstacles detected nearby. Area is clear."

        elif handler == "direction":
            if not dets: return "All directions are clear. You can move freely."
            blocked = set(d["dir"] for d in dets if d["distM"] < self.NEAR_T)
            free = [d for d in ["ahead","left","right","behind"] if d not in blocked]
            if "ahead" not in blocked: return "Path ahead is clear. Continue forward."
            elif free: return f"Path ahead is blocked. Suggest moving {free[0]}."
            return "All directions have obstacles nearby. Stop and wait."

        elif handler == "stop":
            if dangers: return "Stopping! Danger detected. Do not move until area is clear."
            return "Stop command received. Standing by. Say status for surroundings."

        elif handler == "clear":
            if clear: return "Yes, the path ahead is clear. Safe to move forward."
            elif ahead:
                a = ahead[0]
                return f"No — {a['label']} ahead at {a['distM']:.1f} metres. Proceed with caution."
            return "Path ahead appears clear."

        elif handler == "location":
            if gsm_lat and gsm_lon:
                return f"Your location: latitude {gsm_lat:.4f}, longitude {gsm_lon:.4f}. GPS active."
            return "GPS not available. Enable GSM tracker in Tab 4."

        elif handler == "help":
            return ("Commands: am i safe, status, nearest, which way, "
                    "stop, is path clear, where am i, help.")

        else:
            return f"Command not recognised: '{cmd_lower}'. Say 'help' for commands list."


# ═══════════════════════════════════════════════════════════════════════════
#  A* PLANNER
# ═══════════════════════════════════════════════════════════════════════════
class AStarPlanner:
    def __init__(self, cols, rows):
        self.cols=cols; self.rows=rows
        self.grid=[[0]*cols for _ in range(rows)]

    def set(self,c,r,v=1):
        if 0<=c<self.cols and 0<=r<self.rows: self.grid[r][c]=v

    def blocked(self,c,r):
        return c<0 or c>=self.cols or r<0 or r>=self.rows or self.grid[r][c]==1

    def h(self,a,b):
        dx,dy=abs(a[0]-b[0]),abs(a[1]-b[1])
        return max(dx,dy)+(math.sqrt(2)-1)*min(dx,dy)

    def find(self,start,goal):
        if self.blocked(*goal) or self.blocked(*start): return [],[]
        open_set=[(0,start)]; heapq.heapify(open_set)
        came={}; g={start:0}; visited=[]; seen={start}
        D8=[(0,1),(0,-1),(1,0),(-1,0),(1,1),(1,-1),(-1,1),(-1,-1)]
        while open_set:
            _,cur=heapq.heappop(open_set); seen.discard(cur)
            if cur==goal:
                p=[]; c2=cur
                while c2 in came: p.append(c2); c2=came[c2]
                p.append(start); p.reverse(); return p,visited
            visited.append(cur)
            for dc,dr in D8:
                nb=(cur[0]+dc,cur[1]+dr)
                if self.blocked(*nb): continue
                cost=math.sqrt(2) if dc and dr else 1.0
                ng=g[cur]+cost
                if ng<g.get(nb,1e18):
                    came[nb]=cur; g[nb]=ng; f=ng+self.h(nb,goal)
                    if nb not in seen: heapq.heappush(open_set,(f,nb)); seen.add(nb)
        return [],visited


# ═══════════════════════════════════════════════════════════════════════════
#  GSM HELPERS
# ═══════════════════════════════════════════════════════════════════════════
MAP_LAT_MIN,MAP_LAT_MAX=30.8900,30.9100
MAP_LON_MIN,MAP_LON_MAX=75.8400,75.8700

WAYPOINTS=[
    (30.8920,75.8430),(30.8940,75.8460),(30.8955,75.8490),(30.8970,75.8520),
    (30.8975,75.8550),(30.8960,75.8580),(30.8945,75.8610),(30.8930,75.8640),
    (30.8920,75.8660),(30.8935,75.8640),(30.8950,75.8610),(30.8965,75.8580),
    (30.8980,75.8550),(30.8990,75.8520),(30.8980,75.8490),(30.8960,75.8460),
    (30.8940,75.8440),(30.8920,75.8430),
]
POIS=[
    {"name":"Home",   "lat":30.8920,"lon":75.8430,"color":GREEN},
    {"name":"Market", "lat":30.8975,"lon":75.8550,"color":ORANGE},
    {"name":"Hospital","lat":30.8945,"lon":75.8610,"color":RED},
    {"name":"Bus Stop","lat":30.8990,"lon":75.8520,"color":ACCENT},
    {"name":"Park",   "lat":30.8955,"lon":75.8490,"color":"#26A69A"},
]

def hav_m(la1,lo1,la2,lo2):
    R=6371000; p1,p2=math.radians(la1),math.radians(la2)
    dp,dl=math.radians(la2-la1),math.radians(lo2-lo1)
    a=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R*2*math.atan2(math.sqrt(a),math.sqrt(1-a))

def bearing(la1,lo1,la2,lo2):
    dl=math.radians(lo2-lo1)
    x=math.sin(dl)*math.cos(math.radians(la2))
    y=(math.cos(math.radians(la1))*math.sin(math.radians(la2))
       -math.sin(math.radians(la1))*math.cos(math.radians(la2))*math.cos(dl))
    return (math.degrees(math.atan2(x,y))+360)%360

def hdg_name(d):
    return ["N","NE","E","SE","S","SW","W","NW","N"][round(d/45)%8]


# ═══════════════════════════════════════════════════════════════════════════
#  LIDAR GEOMETRY
# ═══════════════════════════════════════════════════════════════════════════
def seg_hit(px,py,dx,dy,ax,ay,bx,by):
    d=dx*(by-ay)-dy*(bx-ax)
    if abs(d)<1e-10: return None
    t=((ax-px)*(by-ay)-(ay-py)*(bx-ax))/d
    u=((ax-px)*dy-(ay-py)*dx)/d
    return t if t>=0 and 0<=u<=1 else None

def circ_hit(px,py,dx,dy,cx,cy,r):
    fx,fy=px-cx,py-cy
    a=dx*dx+dy*dy; b=2*(fx*dx+fy*dy); c=fx*fx+fy*fy-r*r
    disc=b*b-4*a*c
    if disc<0: return None
    sq=math.sqrt(disc); t1=(-b-sq)/(2*a); t2=(-b+sq)/(2*a)
    t=t1 if t1>=0 else (t2 if t2>=0 else None)
    return t

def get_dir(angle,pa):
    rel=((angle-pa)%(2*math.pi)+2*math.pi)%(2*math.pi)
    deg=math.degrees(rel)
    if deg<22.5 or deg>337.5: return "ahead"
    if deg<67.5:  return "ahead-right"
    if deg<112.5: return "right"
    if deg<157.5: return "behind-right"
    if deg<202.5: return "behind"
    if deg<247.5: return "behind-left"
    if deg<292.5: return "left"
    return "ahead-left"

PRESET_OBS=[
    {"type":"rect",  "x":180,"y":130,"w":90,"h":18, "color":"#D84315","label":"Wall"},
    {"type":"rect",  "x":380,"y":130,"w":90,"h":18, "color":"#D84315","label":"Wall"},
    {"type":"rect",  "x":120,"y":130,"w":18,"h":200,"color":"#D84315","label":"Wall"},
    {"type":"rect",  "x":422,"y":130,"w":18,"h":200,"color":"#D84315","label":"Wall"},
    {"type":"circle","x":280,"y":260,"r":22,         "color":"#5C6BC0","label":"Pillar"},
    {"type":"rect",  "x":200,"y":360,"w":60,"h":30, "color":ORANGE,   "label":"Bench"},
    {"type":"circle","x":380,"y":340,"r":16,         "color":"#26A69A","label":"Bin"},
    {"type":"rect",  "x":330,"y":200,"w":25,"h":55, "color":PURPLE,   "label":"Door"},
    {"type":"rect",  "x":150,"y":400,"w":40,"h":15, "color":"#8D6E63","label":"Step"},
    {"type":"circle","x":420,"y":240,"r":12,         "color":RED,      "label":"Post"},
]


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN APP
# ═══════════════════════════════════════════════════════════════════════════
class SmartCaneApp:
    def _play_alert(self, freq, duration):
        """Helper to play a hardware beep without freezing the UI."""
        try:
            import winsound
            # Runs in a separate thread so the GUI doesn't 'hitch'
            threading.Thread(target=lambda: winsound.Beep(freq, duration), daemon=True).start()
        except ImportError:
            # Fallback for Mac/Linux
            self.root.bell()
    def __init__(self, root):
        self.root=root
        self.root.title("Smart Walking Cane Simulator v2")
        self.root.configure(bg=PANEL)
        self.root.resizable(False,False)

        self.voice       = VoiceEngine()
        self.speech      = SpeechGen()
        self.tts_enabled = tk.BooleanVar(value=TTS_OK)
        self.live_scan   = {"detections":[],"clear_ahead":True,"nearest":None}
        self.g_lat=WAYPOINTS[0][0]; self.g_lon=WAYPOINTS[0][1]

        self._build_header()
        self._build_tabs()
        self._build_statusbar()
        self._lidar_init()
        self._route_init()
        self._gsm_init()
        self._lidar_loop()
        self.root.bind("<q>", lambda e: self._quit())

    # ── header ──────────────────────────────────────────────────────────────
    def _build_header(self):
        h=tk.Frame(self.root,bg="#0d1020",pady=8); h.pack(fill="x")
        tk.Label(h,text="Smart Walking Cane Simulator",fg=ACCENT,bg="#0d1020",
                 font=("Courier",16,"bold")).pack(side="left",padx=16)
        tk.Label(h,text="LiDAR | Voice Commands | A* Route | GSM Track",
                 fg=MUTED,bg="#0d1020",font=("Courier",10)).pack(side="left",padx=8)
        tk.Label(h,text="Q to quit",fg="#444466",bg="#0d1020",
                 font=("Courier",9)).pack(side="right",padx=16)

    # ── tabs ─────────────────────────────────────────────────────────────────
    def _build_tabs(self):
        s=ttk.Style(); s.theme_use("default")
        s.configure("TNotebook",background=PANEL,borderwidth=0)
        s.configure("TNotebook.Tab",background="#2a2f45",foreground=WHITE,
                    font=("Courier",10),padding=[12,5])
        s.map("TNotebook.Tab",background=[("selected","#0d1020")],
              foreground=[("selected",ACCENT)])
        self.nb=ttk.Notebook(self.root)
        self.nb.pack(fill="both",expand=True,padx=8,pady=(4,0))
        self.tab_lidar =tk.Frame(self.nb,bg=PANEL)
        self.tab_voice =tk.Frame(self.nb,bg=PANEL)
        self.tab_route =tk.Frame(self.nb,bg=PANEL)
        self.tab_gsm   =tk.Frame(self.nb,bg=PANEL)
        self.tab_access=tk.Frame(self.nb,bg=PANEL)
        self.nb.add(self.tab_lidar, text=" LiDAR Scanner ")
        self.nb.add(self.tab_voice, text=" Voice / Commands ")
        self.nb.add(self.tab_route, text=" A* Route Planner ")
        self.nb.add(self.tab_gsm,   text=" GSM Tracker ")
        self.nb.add(self.tab_access,text=" Accessibility ")
        self._build_lidar_tab()
        self._build_voice_tab()
        self._build_route_tab()
        self._build_gsm_tab()
        self._build_access_tab()

    def _build_statusbar(self):
        self.status_var=tk.StringVar(value="System ready.")
        tk.Label(self.root,textvariable=self.status_var,fg=MUTED,bg="#0d1020",
                 font=("Courier",9),anchor="w").pack(fill="x",padx=12,pady=(0,4))

    # ═══════════════════════════════════════════════════════════════════════
    #  TAB 1 — LIDAR
    # ═══════════════════════════════════════════════════════════════════════
    def _build_lidar_tab(self):
        t=self.tab_lidar
        left=tk.Frame(t,bg=PANEL); left.pack(side="left",padx=8,pady=8)
        right=tk.Frame(t,bg=PANEL); right.pack(side="left",padx=(0,8),pady=8,anchor="n")
        self.lc=tk.Canvas(left,width=600,height=500,bg=DARK,
                          highlightthickness=1,highlightbackground="#333655",cursor="crosshair")
        self.lc.pack()
        self.lc.bind("<Motion>",self._l_mouse)
        self.lc.bind("<Button-1>",self._l_click)
        for label,mn,mx,val,res,attr in [("Sweep °",60,360,180,10,"l_sweep"),
                                          ("Range m",1,8,4,1,"l_range"),
                                          ("Rays",12,120,60,4,"l_rays")]:
            f=tk.Frame(right,bg=PANEL); f.pack(fill="x",pady=3)
            tk.Label(f,text=label,fg=MUTED,bg=PANEL,font=("Courier",10),
                     width=9,anchor="w").pack(side="left")
            v=tk.IntVar(value=val) if res==1 else tk.DoubleVar(value=val)
            tk.Scale(f,from_=mn,to=mx,orient="horizontal",variable=v,resolution=res,
                     bg=PANEL,fg=WHITE,troughcolor="#2a2f45",highlightthickness=0,
                     sliderlength=14,length=120,showvalue=True,bd=0,
                     font=("Courier",9)).pack(side="left")
            setattr(self,attr,v)
        for text,cmd in [("+ Obstacle",self._l_add),("Clear",self._l_clear),
                         ("Preset",self._l_preset),("Auto-move",self._l_toggle_move)]:
            tk.Button(right,text=text,command=cmd,**BTN).pack(fill="x",pady=3)
        tk.Label(right,text="",fg=PANEL,bg=PANEL).pack(pady=2)
        tk.Label(right,text="SENSOR STATUS",fg="#555888",bg=PANEL,
                 font=("Courier",10)).pack(anchor="w")
        self.l_stat={}
        for k,ltext in [("nearest","Nearest"),("dir","Direction"),
                        ("threats","Threats"),("clear","Clear ahead")]:
            f=tk.Frame(right,bg=PANEL); f.pack(fill="x",pady=1)
            tk.Label(f,text=ltext,fg=MUTED,bg=PANEL,font=("Courier",9),
                     width=12,anchor="w").pack(side="left")
            v=tk.StringVar(value="—"); self.l_stat[k]=v
            tk.Label(f,textvariable=v,fg=GREEN,bg=PANEL,
                     font=("Courier",9,"bold")).pack(side="left")
        tk.Label(right,text="",fg=PANEL,bg=PANEL).pack(pady=2)
        tk.Label(right,text="NAVIGATION SPEECH",fg="#555888",bg=PANEL,
                 font=("Courier",10)).pack(anchor="w")
        self.l_speech=tk.Text(right,width=28,height=5,bg=CARD,fg=ACCENT,
                              font=("Courier",9),relief="flat",bd=4,wrap="word")
        self.l_speech.pack(pady=4)
        self.l_speech.insert("1.0","Initializing...")
        self.l_speech.config(state="disabled")

    def _lidar_init(self):
        self.l_person={"x":300,"y":250,"angle":-math.pi/2}
        self.l_obs=[]; self.l_moving=False; self.l_mvangle=0.0; self.l_sticker=0
        self._l_preset()

    def _l_mouse(self,e):
        dx=e.x-self.l_person["x"]; dy=e.y-self.l_person["y"]
        if abs(dx)>2 or abs(dy)>2: self.l_person["angle"]=math.atan2(dy,dx)

    def _l_click(self,e):
        self.l_person["x"]=e.x; self.l_person["y"]=e.y

    def _l_add(self):
        x=random.randint(60,540); y=random.randint(60,440)
        col=random.choice(OBS_COLORS); lb=random.choice(OBS_LABELS)
        if random.random()>0.5:
            self.l_obs.append({"type":"rect","x":x,"y":y,
                               "w":random.randint(30,70),"h":random.randint(20,45),
                               "color":col,"label":lb})
        else:
            self.l_obs.append({"type":"circle","x":x,"y":y,
                               "r":random.randint(12,26),"color":col,"label":lb})

    def _l_clear(self): self.l_obs=[]
    def _l_preset(self):
        self.l_obs=[dict(o) for o in PRESET_OBS]
        self.l_person={"x":300,"y":250,"angle":-math.pi/2}

    def _l_toggle_move(self):
        self.l_moving=not self.l_moving
        if self.l_moving: self.l_mvangle=random.uniform(0,2*math.pi)

    def _cast(self,px,py,angle):
        dx,dy=math.cos(angle),math.sin(angle)
        max_t=self.l_range.get()*SCALE; mt,ho=max_t,None
        for obs in self.l_obs:
            if obs["type"]=="rect":
                for ax,ay,bx,by in [(obs["x"],obs["y"],obs["x"]+obs["w"],obs["y"]),
                                     (obs["x"]+obs["w"],obs["y"],obs["x"]+obs["w"],obs["y"]+obs["h"]),
                                     (obs["x"]+obs["w"],obs["y"]+obs["h"],obs["x"],obs["y"]+obs["h"]),
                                     (obs["x"],obs["y"]+obs["h"],obs["x"],obs["y"])]:
                    t=seg_hit(px,py,dx,dy,ax,ay,bx,by)
                    if t and t<mt: mt,ho=t,obs
            else:
                t=circ_hit(px,py,dx,dy,obs["x"],obs["y"],obs["r"])
                if t and t<mt: mt,ho=t,obs
        return mt,ho,px+dx*mt,py+dy*mt

    def _lidar_loop(self):
        self._lidar_draw()
        self.root.after(33,self._lidar_loop)

    def _lidar_draw(self):
        if self.l_moving:
            p=self.l_person
            p["x"]+=math.cos(self.l_mvangle)*1.4; p["y"]+=math.sin(self.l_mvangle)*1.0
            p["angle"]=self.l_mvangle
            if p["x"]<50 or p["x"]>550 or p["y"]<50 or p["y"]>450:
                self.l_mvangle+=math.pi*(0.5+random.random()*0.5)
            p["x"]=max(50,min(550,p["x"])); p["y"]=max(50,min(450,p["y"]))
        c=self.lc; c.delete("all")
        for gx in range(0,601,SCALE): c.create_line(gx,0,gx,500,fill="#151520")
        for gy in range(0,501,SCALE): c.create_line(0,gy,600,gy,fill="#151520")
        for obs in self.l_obs:
            col=obs["color"]
            if obs["type"]=="rect":
                c.create_rectangle(obs["x"],obs["y"],obs["x"]+obs["w"],obs["y"]+obs["h"],
                                   fill=col,outline=col,width=1.5)
                c.create_text(obs["x"]+obs["w"]//2,obs["y"]+obs["h"]//2,
                              text=obs["label"],fill="white",font=("Courier",9))
            else:
                c.create_oval(obs["x"]-obs["r"],obs["y"]-obs["r"],
                              obs["x"]+obs["r"],obs["y"]+obs["r"],
                              fill=col,outline=col,width=1.5)
                c.create_text(obs["x"],obs["y"],text=obs["label"],fill="white",font=("Courier",9))
        px,py=self.l_person["x"],self.l_person["y"]; pa=self.l_person["angle"]
        sw=self.l_sweep.get()*math.pi/180; nr=int(self.l_rays.get())
        nt=1.5*SCALE; detections=[]
        for i in range(nr):
            a=pa-sw/2+i*sw/max(nr-1,1)
            t,obs,hx,hy=self._cast(px,py,a)
            rc=("#a83030" if obs and t<nt else "#1a5f7a" if obs else "#0d3a4a")
            c.create_line(px,py,hx,hy,fill=rc,width=0.8)
            if obs:
                c.create_oval(hx-3,hy-3,hx+3,hy+3,
                              fill=("#FF7043" if t<nt else "#FFB74D"),outline="")
                detections.append({"distM":t/SCALE,"dir":get_dir(a,pa),"label":obs["label"]})
        c.create_oval(px-13,py-13,px+13,py+13,fill=YELLOW,outline="white",width=1.5)
        ax=px+math.cos(pa)*17; ay=py+math.sin(pa)*17
        c.create_line(px,py,ax,ay,fill="white",width=2,arrow="last")
        cx2=px+math.cos(pa+0.5)*22; cy2=py+math.sin(pa+0.5)*22
        c.create_line(px+5,py+5,cx2,cy2,fill="#cccccc",width=2)
        grouped={}
        for d in detections:
            k=d["dir"]+d["label"]
            if k not in grouped or d["distM"]<grouped[k]["distM"]: grouped[k]=d
        uniq=sorted(grouped.values(),key=lambda x:x["distM"])
        nearest=uniq[0] if uniq else None
        dangers=[d for d in uniq if d["distM"]<=1.0]
        ahead=[d for d in uniq if "ahead" in d["dir"]]
        clear=not ahead or ahead[0]["distM"]>2.0
        self.live_scan={"detections":uniq,"clear_ahead":clear,"nearest":nearest}
        if nearest:
            dm=nearest["distM"]
            self.l_stat["nearest"].set(f"{dm:.1f}m")
            self.l_stat["dir"].set(nearest["dir"])
        else:
            self.l_stat["nearest"].set(f">{self.l_range.get()}m")
            self.l_stat["dir"].set("—")
        self.l_stat["threats"].set(str(len(dangers)))
        self.l_stat["clear"].set("Yes" if clear else "No")
        # --- FIXED VOICE TRIGGER LOGIC ---
       # --- ENHANCED AUDIO & VOICE TRIGGER LOGIC ---
        self.l_sticker -= 1
        
        # Determine current state
        is_danger = len(dangers) > 0
        is_blocked = not clear

        if self.l_sticker <= 0:
            # 1. Trigger the Beep
            if is_danger:
                self._play_alert(1200, 150) # High pitch for Danger
                self.l_sticker = 15         # Rapid Beep (~0.5s interval)
            elif is_blocked:
                self._play_alert(600, 150)  # Low pitch for Caution
                self.l_sticker = 45         # Slower Beep (~1.5s interval)
            else:
                self.l_sticker = 90         # Idle check (~3s interval)

            # 2. Trigger the Speech
            speech = self.speech.generate(self.live_scan)
            if is_danger or is_blocked or self.speech.should_speak(speech):
                self.l_speech.config(state="normal")
                self.l_speech.delete("1.0", "end")
                self.l_speech.insert("1.0", speech)
                self.l_speech.config(state="disabled")
                
                if self.tts_enabled.get():
                    self.voice.speak(speech, priority=is_danger)

            # Update status bar
            safety_word = "DANGER" if is_danger else ("CAUTION" if is_blocked else "SAFE")
            self.status_var.set(f"LiDAR | {len(uniq)} obstacles | {safety_word} | {speech[:55]}...")
    # ═══════════════════════════════════════════════════════════════════════
    #  TAB 2 — VOICE COMMANDS
    # ═══════════════════════════════════════════════════════════════════════
    def _build_voice_tab(self):
        t=self.tab_voice
        tk.Label(t,text="Voice Navigation & Command Input",
                 fg=ACCENT,bg=PANEL,font=("Courier",13,"bold")).pack(anchor="w",padx=16,pady=(12,2))
        tk.Label(t,text="Type a command — the cane responds using live LiDAR data",
                 fg=MUTED,bg=PANEL,font=("Courier",10)).pack(anchor="w",padx=16,pady=(0,8))

        # ── command input box ──────────────────────────────────────────────
        cmd_outer=tk.Frame(t,bg=CARD,highlightthickness=1,highlightbackground=ACCENT)
        cmd_outer.pack(fill="x",padx=16,pady=4)
        tk.Label(cmd_outer,text="VOICE COMMAND INPUT",fg=ACCENT,bg=CARD,
                 font=("Courier",10,"bold")).pack(anchor="w",padx=10,pady=(8,2))
        input_row=tk.Frame(cmd_outer,bg=CARD); input_row.pack(fill="x",padx=10,pady=(0,8))
        self.cmd_var=tk.StringVar()
        self.cmd_entry=tk.Entry(input_row,textvariable=self.cmd_var,width=42,
                                bg="#0d1020",fg=WHITE,font=("Courier",12),
                                insertbackground=ACCENT,relief="flat",
                                highlightthickness=1,highlightcolor=ACCENT,
                                highlightbackground="#333655")
        self.cmd_entry.pack(side="left",ipady=6,padx=(0,8))
        self.cmd_entry.bind("<Return>",lambda e:self._run_command())
        self.cmd_entry.insert(0,"am i safe")
        tk.Button(input_row,text="Send Command",command=self._run_command,**BTN_GREEN).pack(side="left",padx=2)
        tk.Button(input_row,text="Clear",command=lambda:self.cmd_var.set(""),**BTN).pack(side="left",padx=2)

        # quick command buttons
        tk.Label(cmd_outer,text="Quick commands:",fg=MUTED,bg=CARD,
                 font=("Courier",10)).pack(anchor="w",padx=10)
        r1=tk.Frame(cmd_outer,bg=CARD); r1.pack(fill="x",padx=10,pady=3)
        r2=tk.Frame(cmd_outer,bg=CARD); r2.pack(fill="x",padx=10,pady=(0,10))
        cmds=[("am i safe",BTN_GREEN),("status",BTN),("nearest",BTN),("which way",BTN),
              ("stop",BTN_RED),("where am i",BTN),("is path clear",BTN),("help",BTN)]
        for i,(text,style) in enumerate(cmds):
            row=r1 if i<4 else r2
            tk.Button(row,text=text,command=lambda c=text:self._run_specific(c),
                      **style).pack(side="left",padx=3,pady=2)

        # response display
        tk.Label(t,text="COMMAND RESPONSE:",fg="#555888",bg=PANEL,
                 font=("Courier",10)).pack(anchor="w",padx=16,pady=(8,2))
        self.cmd_response=tk.Text(t,width=80,height=4,bg=CARD,fg="#56d364",
                                  font=("Courier",11,"bold"),relief="flat",bd=6,wrap="word")
        self.cmd_response.pack(padx=16,pady=(0,4))
        self.cmd_response.insert("1.0","Waiting for command...")
        self.cmd_response.config(state="disabled")

        # live safety indicator
        ind_row=tk.Frame(t,bg=PANEL); ind_row.pack(fill="x",padx=16,pady=4)
        tk.Label(ind_row,text="Live safety status:",fg=MUTED,bg=PANEL,
                 font=("Courier",10)).pack(side="left")
        self.safety_ind=tk.Label(ind_row,text="● SAFE",fg=GREEN,bg=PANEL,
                                  font=("Courier",13,"bold"))
        self.safety_ind.pack(side="left",padx=8)
        self._update_safety_indicator()

        # mode + api key
        mode_f=tk.Frame(t,bg=PANEL); mode_f.pack(fill="x",padx=16,pady=4)
        tk.Label(mode_f,text="Auto-speech:",fg=MUTED,bg=PANEL,font=("Courier",10)).pack(side="left")
        self.voice_mode=tk.StringVar(value="rule_based")
        for val,txt in [("rule_based","Offline"),("openai","OpenAI GPT"),("ollama","Ollama")]:
            tk.Radiobutton(mode_f,text=txt,variable=self.voice_mode,value=val,fg=WHITE,
                           bg=PANEL,selectcolor="#2a2f45",activebackground=PANEL,
                           font=("Courier",10),command=self._update_voice_mode).pack(side="left",padx=6)
        key_f=tk.Frame(t,bg=PANEL); key_f.pack(fill="x",padx=16,pady=2)
        tk.Label(key_f,text="OpenAI key:",fg=MUTED,bg=PANEL,font=("Courier",10)).pack(side="left")
        self.api_key_var=tk.StringVar()
        tk.Entry(key_f,textvariable=self.api_key_var,width=40,bg=CARD,fg=WHITE,
                 font=("Courier",10),insertbackground=WHITE,relief="flat").pack(side="left",padx=6)
        tk.Button(key_f,text="Apply",command=self._apply_api_key,**BTN).pack(side="left")
        tts_f=tk.Frame(t,bg=PANEL); tts_f.pack(fill="x",padx=16,pady=2)
        tk.Checkbutton(tts_f,text="Enable audio speech (pyttsx3)",variable=self.tts_enabled,
                       fg=WHITE,bg=PANEL,selectcolor="#2a2f45",activebackground=PANEL,
                       font=("Courier",10)).pack(side="left")
        if not TTS_OK:
            tk.Label(tts_f,text="  [pip install pyttsx3]",fg=ORANGE,bg=PANEL,
                     font=("Courier",9)).pack(side="left")

        # speech log
        tk.Label(t,text="Speech log:",fg=MUTED,bg=PANEL,
                 font=("Courier",10)).pack(anchor="w",padx=16,pady=(8,2))
        self.voice_log=scrolledtext.ScrolledText(t,width=80,height=7,bg=CARD,fg=ACCENT,
                                                  font=("Courier",9),relief="flat")
        self.voice_log.pack(padx=16,pady=(0,8))
        self.voice_log.insert("1.0","[Log — auto-speech and command responses appear here]\n")

    def _run_command(self):
        cmd=self.cmd_var.get().strip()
        if cmd: self._process_command(cmd)

    def _run_specific(self,cmd):
        self.cmd_var.set(cmd); self._process_command(cmd)

    def _process_command(self,cmd):
        response=self.speech.handle_command(
            cmd, self.live_scan,
            gsm_lat=self.g_lat, gsm_lon=self.g_lon)
        self.cmd_response.config(state="normal")
        self.cmd_response.delete("1.0","end")
        self.cmd_response.insert("1.0",response)
        if any(w in response.upper() for w in ["STOP","DANGER","NOT SAFE","ALERT"]):
            self.cmd_response.config(fg="#f85149")
        elif any(w in response.lower() for w in ["caution","slow","near"]):
            self.cmd_response.config(fg=ORANGE)
        else:
            self.cmd_response.config(fg="#56d364")
        self.cmd_response.config(state="disabled")
        if self.tts_enabled.get(): self.voice.speak(response,priority=True)
        self._log_voice(f"CMD [{cmd}] → {response}","cmd")
        self.status_var.set(f"Command: '{cmd}' | {response[:70]}...")

    def _update_safety_indicator(self):
        dets=self.live_scan.get("detections",[])
        dangers=[d for d in dets if d["distM"]<=1.0]
        warnings=[d for d in dets if d["distM"]<=2.0]
        if dangers: self.safety_ind.config(text="● DANGER — STOP!",fg=RED)
        elif warnings: self.safety_ind.config(text="● CAUTION",fg=ORANGE)
        else: self.safety_ind.config(text="● SAFE",fg=GREEN)
        self.root.after(500,self._update_safety_indicator)

    def _update_voice_mode(self):
        self.speech=SpeechGen(mode=self.voice_mode.get(),api_key=self.api_key_var.get().strip() or None)
        self._log_voice(f"[Mode → {self.voice_mode.get()}]","sys")

    def _apply_api_key(self):
        self.speech=SpeechGen(mode=self.voice_mode.get(),api_key=self.api_key_var.get().strip())
        self._log_voice("[API key applied]","sys")

    def _log_voice(self,text,tag="auto"):
        ts=time.strftime("%H:%M:%S")
        prefix={"auto":"AUTO","cmd":"CMD ","sys":"SYS "}.get(tag,"----")
        self.voice_log.insert("end",f"{ts} [{prefix}] {text}\n")
        self.voice_log.see("end")

    # ═══════════════════════════════════════════════════════════════════════
    #  TAB 3 — A* ROUTE
    # ═══════════════════════════════════════════════════════════════════════
    def _build_route_tab(self):
        t=self.tab_route; CELL=18; RC=34; RR=26
        self.R_CELL=CELL; self.R_COLS=RC; self.R_ROWS=RR
        top=tk.Frame(t,bg=PANEL); top.pack(fill="x",padx=8,pady=(8,0))
        tk.Label(top,text="A* Route Planner",fg=ACCENT,bg=PANEL,
                 font=("Courier",12,"bold")).pack(side="left")
        for text,cmd in [("Find Path",self._r_find),("Walk",self._r_walk),
                         ("Preset",self._r_preset),("Random",self._r_random),("Clear",self._r_clear)]:
            tk.Button(top,text=text,command=cmd,**BTN).pack(side="right",padx=3)
        self.rc=tk.Canvas(t,width=RC*CELL,height=RR*CELL,bg=DARK,
                          highlightthickness=1,highlightbackground="#333655")
        self.rc.pack(padx=8,pady=4)
        self.rc.bind("<Button-1>",self._r_click)
        self.rc.bind("<B1-Motion>",self._r_drag)
        self.rc.bind("<Button-3>",self._r_set_goal)
        self.r_status=tk.StringVar(value="Left click: draw walls  |  Right click: set goal")
        tk.Label(t,textvariable=self.r_status,fg=MUTED,bg=PANEL,font=("Courier",9)).pack(pady=2)

    def _route_init(self):
        self.r_planner=AStarPlanner(self.R_COLS,self.R_ROWS)
        self.r_start=(2,self.R_ROWS//2); self.r_goal=(self.R_COLS-3,self.R_ROWS//2)
        self.r_path=[]; self.r_visited=[]; self.r_person=self.r_start
        self.r_animating=False; self.r_step=0; self._r_preset()

    def _r_cell(self,x,y): return (int(x//self.R_CELL),int(y//self.R_CELL))
    def _r_ctr(self,c,r):  return (c*self.R_CELL+self.R_CELL//2,r*self.R_CELL+self.R_CELL//2)

    def _r_click(self,e):
        cell=self._r_cell(e.x,e.y)
        if cell not in (self.r_start,self.r_goal):
            self.r_planner.set(*cell,0 if self.r_planner.blocked(*cell) else 1)
            self.r_path=[]; self._r_draw()

    def _r_drag(self,e):
        cell=self._r_cell(e.x,e.y)
        if cell not in (self.r_start,self.r_goal):
            self.r_planner.set(*cell,1); self.r_path=[]; self._r_draw()

    def _r_set_goal(self,e):
        cell=self._r_cell(e.x,e.y)
        if not self.r_planner.blocked(*cell): self.r_goal=cell; self.r_path=[]; self._r_draw()

    def _r_preset(self):
        self.r_planner=AStarPlanner(self.R_COLS,self.R_ROWS)
        self.r_path=[]; self.r_visited=[]; self.r_person=self.r_start
        for group in [[(c,4) for c in range(4,28)],[(c,22) for c in range(4,28)],
                      [(8,r) for r in range(4,13)],[(8,r) for r in range(16,23)],
                      [(20,r) for r in range(4,10)],[(20,r) for r in range(13,23)],
                      [(14,10),(14,11),(15,10),(15,11)],[(25,7),(25,8),(26,7),(26,8)],
                      [(10,18),(11,18),(12,18)]]:
            for c,r in group: self.r_planner.set(c,r)
        self._r_draw()

    def _r_random(self):
        self.r_planner=AStarPlanner(self.R_COLS,self.R_ROWS)
        self.r_path=[]; self.r_visited=[]; self.r_person=self.r_start
        for r in range(self.R_ROWS):
            for c in range(self.R_COLS):
                if random.random()<0.14 and (c,r) not in (self.r_start,self.r_goal):
                    self.r_planner.set(c,r)
        self._r_draw()

    def _r_clear(self):
        self.r_planner=AStarPlanner(self.R_COLS,self.R_ROWS)
        self.r_path=[]; self.r_visited=[]; self.r_person=self.r_start; self._r_draw()

    def _r_find(self):
        self.r_animating=False; self.r_person=self.r_start
        self.r_path,self.r_visited=self.r_planner.find(self.r_start,self.r_goal)
        self.r_status.set(f"Path found: {len(self.r_path)} steps | Click Walk" if self.r_path else "No path found.")
        self._r_draw()

    def _r_walk(self):
        if not self.r_path: self._r_find()
        if not self.r_path: return
        self.r_step=0; self.r_person=self.r_start; self.r_animating=True; self._r_animate()

    def _r_animate(self):
        if not self.r_animating: return
        if self.r_step<len(self.r_path):
            self.r_person=self.r_path[self.r_step]; self.r_step+=1
            self.r_status.set(f"Walking {self.r_step}/{len(self.r_path)}")
            self._r_draw(); self.root.after(55,self._r_animate)
        else:
            self.r_animating=False; self.r_status.set("Goal reached!"); self._r_draw()

    def _r_draw(self):
        c=self.rc; CE=self.R_CELL; c.delete("all")
        for col in range(self.R_COLS+1): c.create_line(col*CE,0,col*CE,self.R_ROWS*CE,fill="#151520")
        for row in range(self.R_ROWS+1): c.create_line(0,row*CE,self.R_COLS*CE,row*CE,fill="#151520")
        for col,row in self.r_visited:
            c.create_rectangle(col*CE+1,row*CE+1,col*CE+CE-1,row*CE+CE-1,fill="#1a2a3a",outline="")
        for row in range(self.R_ROWS):
            for col in range(self.R_COLS):
                if self.r_planner.grid[row][col]:
                    c.create_rectangle(col*CE,row*CE,col*CE+CE,row*CE+CE,fill="#8B2500",outline="#D84315",width=0.5)
        if len(self.r_path)>1:
            pts=[]
            for pt in self.r_path: px2,py2=self._r_ctr(*pt); pts+=[px2,py2]
            c.create_line(*pts,fill="#4FC3F7",width=2,capstyle="round",joinstyle="round")
        gx,gy=self._r_ctr(*self.r_goal)
        c.create_rectangle(self.r_goal[0]*CE+2,self.r_goal[1]*CE+2,
                           self.r_goal[0]*CE+CE-2,self.r_goal[1]*CE+CE-2,
                           fill="#2d6b30",outline="#66BB6A",width=2)
        c.create_text(gx,gy,text="G",fill="white",font=("Courier",9,"bold"))
        px2,py2=self._r_ctr(*self.r_person)
        c.create_oval(px2-8,py2-8,px2+8,py2+8,fill=YELLOW,outline="white",width=1.5)
        c.create_text(px2,py2,text="P",fill="#333",font=("Courier",8,"bold"))

    # ═══════════════════════════════════════════════════════════════════════
    #  TAB 4 — GSM TRACKER
    # ═══════════════════════════════════════════════════════════════════════
    def _build_gsm_tab(self):
        t=self.tab_gsm; self.G_W=560; self.G_H=440
        main=tk.Frame(t,bg=PANEL); main.pack(padx=8,pady=8)
        left=tk.Frame(main,bg=PANEL); left.pack(side="left",padx=(0,8))
        right=tk.Frame(main,bg=PANEL); right.pack(side="left",anchor="n")
        tk.Label(left,text="Live GPS Map  [simulated GSM + Neo-6M]",
                 fg=ACCENT,bg=PANEL,font=("Courier",11,"bold")).pack(anchor="w",pady=(0,4))
        self.gc=tk.Canvas(left,width=self.G_W,height=self.G_H,bg=DARK,
                          highlightthickness=1,highlightbackground="#333655")
        self.gc.pack()
        self.g_stat={}
        def sv(key,init="—"):
            v=tk.StringVar(value=init); self.g_stat[key]=v; return v
        for label,var,fg in [("Latitude",sv("lat"),ACCENT),("Longitude",sv("lon"),ACCENT),
                               ("Speed",sv("spd"),YELLOW),("Heading",sv("hdg"),YELLOW),
                               ("Distance",sv("dst"),YELLOW),("Elapsed",sv("ela"),YELLOW),
                               ("Nearest POI",sv("poi"),PURPLE),("POI dist",sv("pod"),PURPLE),
                               ("GSM signal",sv("sig","3/5"),GREEN)]:
            f=tk.Frame(right,bg=PANEL); f.pack(fill="x",pady=2)
            tk.Label(f,text=label,fg=MUTED,bg=PANEL,font=("Courier",10),width=13,anchor="w").pack(side="left")
            tk.Label(f,textvariable=var,fg=fg,bg=PANEL,font=("Courier",10,"bold")).pack(side="left")
        bf=tk.Frame(right,bg=PANEL); bf.pack(pady=8)
        self.g_btn=tk.Button(bf,text="▶ Start Tracking",command=self._g_toggle,**BTN_GREEN)
        self.g_btn.pack(fill="x",pady=3)
        tk.Button(bf,text="Reset",command=self._g_reset,**BTN).pack(fill="x",pady=3)
        exp=tk.Frame(right,bg=CARD); exp.pack(fill="x",pady=4)
        for line in ["GSM module explanation:","Neo-6M GPS → UART → MCU",
                     "SIM800L → cell → cloud","hav_m(): real distance calc",
                     "Update tick: 200ms"]:
            tk.Label(exp,text=line,fg=MUTED,bg=CARD,font=("Courier",8),anchor="w").pack(anchor="w",padx=6,pady=1)

    def _gsm_init(self):
        self.g_lat,self.g_lon=WAYPOINTS[0]
        self.g_wp_idx=0; self.g_wp_t=0.0; self.g_trail=[]
        self.g_tracking=False; self.g_dist=0.0; self.g_start=None
        self._g_draw()

    def _g_lat_y(self,lat): return self.G_H-(lat-MAP_LAT_MIN)/(MAP_LAT_MAX-MAP_LAT_MIN)*self.G_H
    def _g_lon_x(self,lon): return (lon-MAP_LON_MIN)/(MAP_LON_MAX-MAP_LON_MIN)*self.G_W

    def _g_toggle(self):
        self.g_tracking=not self.g_tracking
        if self.g_tracking:
            self.g_btn.config(text="⏸ Pause",bg="#1a3a2a")
            if self.g_start is None: self.g_start=time.time()
            self._g_update()
        else:
            self.g_btn.config(text="▶ Resume",bg="#2a2f45")

    def _g_reset(self):
        self.g_tracking=False; self.g_wp_idx=0; self.g_wp_t=0.0
        self.g_trail=[]; self.g_dist=0.0; self.g_start=None
        self.g_lat,self.g_lon=WAYPOINTS[0]
        self.g_btn.config(text="▶ Start Tracking",bg="#1a4a2a"); self._g_draw()

    def _g_update(self):
        if not self.g_tracking: return
        self.g_wp_t+=0.016+random.uniform(-0.002,0.002)
        if self.g_wp_t>=1.0:
            self.g_wp_t=0.0; self.g_wp_idx=(self.g_wp_idx+1)%(len(WAYPOINTS)-1)
        la1,lo1=WAYPOINTS[self.g_wp_idx]; la2,lo2=WAYPOINTS[self.g_wp_idx+1]
        prev_la,prev_lo=self.g_lat,self.g_lon; n=0.00002
        self.g_lat=la1+(la2-la1)*self.g_wp_t+random.uniform(-n,n)
        self.g_lon=lo1+(lo2-lo1)*self.g_wp_t+random.uniform(-n,n)
        if self.g_trail: self.g_dist+=hav_m(prev_la,prev_lo,self.g_lat,self.g_lon)
        self.g_trail.append((self.g_lat,self.g_lon))
        if len(self.g_trail)>400: self.g_trail=self.g_trail[-400:]
        elapsed=time.time()-self.g_start
        spd=self.g_dist/max(elapsed,1)
        hdg=bearing(prev_la,prev_lo,self.g_lat,self.g_lon)
        poi=min(POIS,key=lambda p:hav_m(self.g_lat,self.g_lon,p["lat"],p["lon"]))
        pdist=hav_m(self.g_lat,self.g_lon,poi["lat"],poi["lon"])
        self.g_stat["lat"].set(f"{self.g_lat:.5f}°")
        self.g_stat["lon"].set(f"{self.g_lon:.5f}°")
        self.g_stat["spd"].set(f"{spd:.2f} m/s")
        self.g_stat["hdg"].set(f"{hdg:.0f}° {hdg_name(hdg)}")
        self.g_stat["dst"].set(f"{self.g_dist:.0f}m")
        self.g_stat["ela"].set(f"{int(elapsed//60)}m {int(elapsed%60)}s")
        self.g_stat["poi"].set(poi["name"])
        self.g_stat["pod"].set(f"{pdist:.0f}m")
        self.g_stat["sig"].set(f"{random.randint(3,5)}/5")
        self._g_draw(); self.root.after(200,self._g_update)

    def _g_draw(self):
        c=self.gc; c.delete("all"); random.seed(42)
        for lat in [30.892,30.894,30.896,30.898]:
            y=self._g_lat_y(lat); c.create_line(0,y,self.G_W,y,fill="#1e2a3a",width=7)
        for lon in [75.844,75.848,75.852,75.856,75.860,75.864]:
            x=self._g_lon_x(lon); c.create_line(x,0,x,self.G_H,fill="#1e2a3a",width=7)
        for _ in range(35):
            la=random.uniform(MAP_LAT_MIN+0.002,MAP_LAT_MAX-0.002)
            lo=random.uniform(MAP_LON_MIN+0.002,MAP_LON_MAX-0.002)
            bx=self._g_lon_x(lo); by=self._g_lat_y(la)
            c.create_rectangle(bx,by,bx+random.randint(10,25),by+random.randint(8,20),
                               fill="#162030",outline="#1a2c3c",width=0.5)
        if len(WAYPOINTS)>1:
            pts=[]
            for la,lo in WAYPOINTS: pts+=[self._g_lon_x(lo),self._g_lat_y(la)]
            c.create_line(*pts,fill="#1e2535",width=2,dash=(4,6))
        if len(self.g_trail)>1:
            pts=[]
            for la,lo in self.g_trail: pts+=[self._g_lon_x(lo),self._g_lat_y(la)]
            c.create_line(*pts,fill=ACCENT,width=2)
        for poi in POIS:
            px2=self._g_lon_x(poi["lon"]); py2=self._g_lat_y(poi["lat"])
            c.create_oval(px2-6,py2-6,px2+6,py2+6,fill=poi["color"],outline=poi["color"],width=1.5)
            c.create_text(px2,py2-12,text=poi["name"],fill=poi["color"],font=("Courier",7))
        px2=self._g_lon_x(self.g_lon); py2=self._g_lat_y(self.g_lat)
        c.create_oval(px2-9,py2-9,px2+9,py2+9,fill=YELLOW,outline="white",width=1.5)
        c.create_oval(px2-18, py2-18, px2+18, py2+18, fill="", outline="#FFD54F", width=1)
        c.create_rectangle(4,4,196,34,fill="#0d1117",outline="")
        c.create_text(8,10,anchor="nw",text=f"Lat:{self.g_lat:.5f}  Lon:{self.g_lon:.5f}",
                      fill="#90CAF9",font=("Courier",8))
        c.create_text(8,23,anchor="nw",
                      text=f"Trail:{len(self.g_trail)}pts  Dist:{self.g_dist:.0f}m",
                      fill="#90CAF9",font=("Courier",8))

    # ═══════════════════════════════════════════════════════════════════════
    #  TAB 5 — ACCESSIBILITY
    # ═══════════════════════════════════════════════════════════════════════
    def _build_access_tab(self):
        t=self.tab_access
        tk.Label(t,text="Accessibility & User-Centric Settings",
                 fg=ACCENT,bg=PANEL,font=("Courier",13,"bold")).pack(anchor="w",padx=16,pady=(12,4))
        sections=[
            ("Audio Alerts",[("Danger beep (< 1m)","beep_danger",True),
                              ("Warning beep (< 2m)","beep_warn",True),
                              ("Path-clear confirmation","beep_clear",False),
                              ("Obstacle count on scan","beep_count",False)]),
            ("Speech Settings",[("High urgency voice","voice_urgent",True),
                                 ("Repeat every 3s","speech_repeat",False),
                                 ("Metric units (m)","units_metric",True),
                                 ("Direction in clock","clock_dir",False)]),
            ("Display",[("Show ray count","show_rays",True),
                        ("Highlight danger zone","show_danger",True),
                        ("Show obstacle labels","show_labels",True),
                        ("Night mode","night_mode",True)]),
            ("Haptic (sim)",[("Vibrate on danger","vib_danger",True),
                              ("Pulse on obstacle","vib_pulse",False),
                              ("Nav confirmation","vib_nav",False),
                              ("GPS tick","vib_gps",False)]),
        ]
        self.access_vars={}
        cols_frame=tk.Frame(t,bg=PANEL); cols_frame.pack(padx=16,pady=8,fill="both")
        for sec_name,opts in sections:
            col=tk.Frame(cols_frame,bg=PANEL); col.pack(side="left",padx=12,anchor="n")
            tk.Label(col,text=sec_name,fg="#555888",bg=PANEL,font=("Courier",10)).pack(anchor="w",pady=(0,4))
            cf=card_frame(col); cf.pack(fill="x")
            for opt_name,key,default in opts:
                v=tk.BooleanVar(value=default); self.access_vars[key]=v
                tk.Checkbutton(cf,text=opt_name,variable=v,fg=WHITE,bg=CARD,
                               selectcolor="#2a2f45",activebackground=CARD,
                               font=("Courier",10),pady=3).pack(anchor="w",padx=8)
        vib_row=tk.Frame(t,bg=PANEL); vib_row.pack(padx=16,pady=8,anchor="w")
        tk.Label(vib_row,text="Haptic motor: ",fg=MUTED,bg=PANEL,font=("Courier",10)).pack(side="left")
        self.vib_canvas=tk.Canvas(vib_row,width=130,height=24,bg=CARD,highlightthickness=0)
        self.vib_canvas.pack(side="left"); self._vib_idle()
        info=tk.Frame(t,bg=CARD); info.pack(padx=16,pady=8,fill="x")
        for line in ["Real hardware map:","  Beep alerts  → Piezo buzzer on GPIO",
                     "  Haptic pulse → Vibration motor (PWM)","  TTS speech   → Speaker + espeak",
                     "  GSM tracker  → SIM800L + Neo-6M GPS","  LiDAR sensor → RPLidar A1 serial"]:
            tk.Label(info,text=line,fg=MUTED,bg=CARD,font=("Courier",9),anchor="w").pack(anchor="w",padx=8,pady=1)

    def _vib_idle(self):
        c=self.vib_canvas; c.delete("all")
        c.create_text(65,12,text="◼◼◼◼◼ idle",fill="#444466",font=("Courier",9))
        self.root.after(4000,self._vib_pulse_demo)

    def _vib_pulse_demo(self):
        c=self.vib_canvas; c.delete("all")
        c.create_text(65,12,text="▓▓▓▓▓ buzz!",fill=ORANGE,font=("Courier",9,"bold"))
        self.root.after(400,self._vib_idle)

    def _quit(self):
        self.voice.stop(); self.root.destroy()


def main():
    root=tk.Tk()
    root.tk.call('tk','scaling',1.1)
    app=SmartCaneApp(root)
    root.protocol("WM_DELETE_WINDOW",app._quit)
    root.mainloop()

if __name__=="__main__":
    main()
