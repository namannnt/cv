class AICoach:
    def generate_feedback(self, summary):
        feedback = []

        avg         = summary["avg_score"]
        distractions = summary["distractions"]
        fatigue     = summary["fatigue_events"]
        focus_time  = summary["focus_time"]  # string like "3m 45s"
        distract_rt = float(summary["distraction_rate"].replace("%", ""))

        # parse focus minutes from string
        try:
            focus_min = int(focus_time.split("m")[0])
        except:
            focus_min = 0

        # score feedback
        if avg > 80:
            feedback.append("🔥 Excellent focus! Your attention was consistently high.")
        elif avg > 60:
            feedback.append("👍 Good focus overall, but some dips detected.")
        elif avg > 40:
            feedback.append("⚠️ Moderate focus. Try reducing background distractions.")
        else:
            feedback.append("🔴 Low focus detected. Consider shorter, more intense sessions.")

        # distraction feedback
        if distract_rt > 40:
            feedback.append("📱 Very high distraction rate. Remove phone/notifications during study.")
        elif distract_rt > 20:
            feedback.append("👀 Frequent distractions. Try facing away from windows or doors.")
        elif distractions < 5:
            feedback.append("✅ Very few distractions — great environment control!")

        # fatigue feedback
        if fatigue > 30:
            feedback.append("😴 Heavy fatigue detected. Use 25-5 Pomodoro breaks.")
        elif fatigue > 10:
            feedback.append("🟠 Some fatigue detected. Blink more often and rest your eyes.")
        else:
            feedback.append("💪 Low fatigue — your energy levels were good this session.")

        # focus time feedback
        if focus_min >= 20:
            feedback.append("⏱ Strong sustained focus — you maintained attention well.")
        elif focus_min >= 10:
            feedback.append("⏳ Moderate focus duration. Try to extend focused blocks.")
        else:
            feedback.append("⌛ Short focus periods. Try eliminating distractions before starting.")

        # smart tip
        if avg < 60 and distract_rt > 30:
            feedback.append("💡 Tip: Try the Pomodoro technique — 25 min focus, 5 min break.")
        elif avg > 75 and fatigue < 5:
            feedback.append("💡 Tip: You're performing well — consider slightly longer sessions.")

        # break recommendations
        if avg < 50:
            feedback.append("⚠️ Consider taking short 5-min breaks every 25 minutes.")
        if fatigue > 3:
            feedback.append("⏳ Take a break now — your brain needs recovery time.")

        return feedback
