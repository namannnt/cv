import os
import json
import threading
from datetime import datetime, timedelta

_stats_lock = threading.Lock()


class Gamification:
    def __init__(self):
        self.file = "data/user_stats.json"
        os.makedirs("data", exist_ok=True)

        if not os.path.exists(self.file):
            self.data = {
                "streak": 0,
                "last_date": "",
                "total_sessions": 0,
                "high_score": 0,
                "total_focus_minutes": 0
            }
            self.save()
        else:
            with open(self.file, "r") as f:
                self.data = json.load(f)

    def save(self):
        with _stats_lock:
            with open(self.file, "w") as f:
                json.dump(self.data, f, indent=4)

    def update(self, avg_score, focus_minutes=0):
        with _stats_lock:
            today     = datetime.now().strftime("%Y-%m-%d")
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

            if self.data["last_date"] == yesterday:
                self.data["streak"] += 1
            elif self.data["last_date"] != today:
                self.data["streak"] = 1

            self.data["last_date"]           = today
            self.data["total_sessions"]      += 1
            self.data["high_score"]          = max(self.data["high_score"], round(avg_score, 1))
            self.data["total_focus_minutes"] = self.data.get("total_focus_minutes", 0) + focus_minutes

            with open(self.file, "w") as f:
                json.dump(self.data, f, indent=4)

    def get_stats(self):
        return self.data

    def get_badges(self):
        badges = []
        streak = self.data["streak"]
        score  = self.data["high_score"]
        sessions = self.data["total_sessions"]
        focus_min = self.data.get("total_focus_minutes", 0)

        if streak >= 3:  badges.append("🔥 3-Day Streak")
        if streak >= 7:  badges.append("🏆 7-Day Warrior")
        if streak >= 30: badges.append("💀 30-Day Legend")

        if score > 85:   badges.append("🎯 Focus Master")
        if score >= 95:  badges.append("🧠 Attention God")

        if sessions >= 5:   badges.append("📚 5 Sessions Done")
        if sessions >= 20:  badges.append("🚀 20 Sessions Pro")

        if focus_min >= 60:  badges.append("⏱ 1 Hour Focused")
        if focus_min >= 300: badges.append("⚡ 5 Hours Legend")

        return badges if badges else []
