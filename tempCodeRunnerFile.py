import tkinter as tk
import threading
import speech_recognition as sr
import pyttsx3
import math

class SmartCaneApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Voice-Enabled LiDAR Simulator")
        
        # Simulator State
        self.canvas = tk.Canvas(root, width=600, height=400, bg="#0a0e1a")
        self.canvas.pack()
        
        # Mock Data (In a real app, these update based on your LiDAR scan)
        self.nearest_obstacle = "Wall"
        self.distance = 1.2  # meters
        self.direction = "ahead-left"

        # Voice Engine
        self.engine = pyttsx3.init()
        self.recognizer = sr.Recognizer()

        # UI Elements
        self.label = tk.Label(root, text="Press 'v' to speak or click button", fg="white", bg="black")
        self.label.pack()
        self.btn = tk.Button(root, text="Listen", command=self.start_voice_thread)
        self.btn.pack()

        # Bind key for easy prototyping
        self.root.bind('<v>', lambda e: self.start_voice_thread())

    def speak(self, text):
        """Non-blocking speech."""
        print(f"Cane says: {text}")
        self.engine.say(text)
        self.engine.runAndWait()

    def start_voice_thread(self):
        """Run listening in background so the GUI doesn't freeze."""
        threading.Thread(target=self.listen_and_respond, daemon=True).start()

    def listen_and_respond(self):
        with sr.Microphone(device_index=2) as source:
            self.root.title("Listening...")
            print("Listening...")
            try:
                audio = self.recognizer.listen(source, timeout=3)
                command = self.recognizer.recognize_google(audio).lower()
                self.process_command(command)
            except Exception as e:
                print("Could not hear you.")
            self.root.title("Voice-Enabled LiDAR Simulator")

def process_command(self, command):
        """Improved Logic Brain with more keywords."""
        print(f"DEBUG: Processing command -> {command}") # See exactly what was heard
        
        # 1. Status / What is around me?
        if any(word in command for word in ["status", "report", "look", "see", "around"]):
            response = f"I detect a {self.nearest_obstacle} about {self.distance} meters to your {self.direction}."
            
        # 2. Safety / Can I move?
        elif any(word in command for word in ["safe", "clear", "go", "walk", "move"]):
            if self.distance < 0.8: # Increased threshold for safety
                response = f"Caution. There is a {self.nearest_obstacle} very close. I do not recommend moving."
            else:
                response = "The path ahead looks clear for about 1 meter."

        # 3. Help Command
        elif "help" in command or "what can you do" in command:
            response = "You can ask me for a status report, or ask if it is safe to walk."

        # 4. Fallback
        else:
            response = f"I heard you say '{command}', but I don't have a programmed response for that yet."
        
        self.speak(response)

if __name__ == "__main__":
    root = tk.Tk()
    app = SmartCaneApp(root)
    root.mainloop()
