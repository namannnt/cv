import pandas as pd
import matplotlib.pyplot as plt


class AnalyticsEngine:
    def __init__(self, file_path):
        self.df = pd.read_csv(file_path)

    def average_score(self):
        return self.df["attention_score"].mean()

    def total_distractions(self):
        return (self.df["state"] == "DISTRACTED").sum()

    def fatigue_events(self):
        return (self.df["fatigue_score"] > 0).sum()

    def focus_time(self):
        # each row = 1 second, so count = seconds
        focused = (self.df["state"] == "FOCUSED").sum()
        return focused  # seconds

    def distraction_rate(self):
        return round((self.total_distractions() / len(self.df)) * 100, 1)

    def get_summary(self):
        focus_sec = self.focus_time()
        return {
            "avg_score":       round(self.average_score(), 2),
            "distractions":    int(self.total_distractions()),
            "distraction_rate": f"{self.distraction_rate()}%",
            "fatigue_events":  int(self.fatigue_events()),
            "focus_time":      f"{focus_sec // 60}m {focus_sec % 60}s",
            "total_duration":  f"{len(self.df) // 60}m {len(self.df) % 60}s",
        }

    def session_quality(self):
        avg         = self.average_score()
        distractions = self.total_distractions()
        fatigue     = self.fatigue_events()
        quality     = (avg * 0.5) - (distractions * 2) - (fatigue * 3)
        return max(0, min(100, round(quality, 2)))

    def focus_decay(self):
        mid          = len(self.df) // 2
        first_half   = self.df["attention_score"][:mid].mean()
        second_half  = self.df["attention_score"][mid:].mean()
        if second_half < first_half - 5:
            return f"📉 Focus decreased over time ({first_half:.0f} → {second_half:.0f})"
        elif second_half > first_half + 5:
            return f"📈 Focus improved over time ({first_half:.0f} → {second_half:.0f})"
        else:
            return f"➡️ Focus stayed consistent ({first_half:.0f} → {second_half:.0f})"

    def distraction_series(self):
        return (self.df["state"] == "DISTRACTED").astype(int)

    def plot_attention(self):
        plt.figure(figsize=(10, 4))
        plt.plot(self.df["attention_score"], color="cyan", linewidth=1.5)
        plt.axhline(y=70, color="green", linestyle="--", alpha=0.5, label="Focused threshold")
        plt.axhline(y=40, color="red",   linestyle="--", alpha=0.5, label="Distracted threshold")
        plt.title("Attention Score Over Session")
        plt.xlabel("Time (seconds)")
        plt.ylabel("Score")
        plt.legend()
        plt.tight_layout()
        plt.show()

    def plot_state_distribution(self):
        counts = self.df["state"].value_counts()
        colors = {
            "FOCUSED": "green", "LOW FOCUS": "yellow",
            "DISTRACTED": "red", "FATIGUED": "orange"
        }
        bar_colors = [colors.get(s, "gray") for s in counts.index]
        plt.figure(figsize=(6, 4))
        counts.plot(kind="bar", color=bar_colors)
        plt.title("State Distribution")
        plt.xlabel("State")
        plt.ylabel("Seconds")
        plt.tight_layout()
        plt.show()
