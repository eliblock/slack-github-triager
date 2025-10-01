from datetime import datetime


def format_relative_time(timestamp: float):
    dt = datetime.fromtimestamp(timestamp)
    now = datetime.now()
    diff = now - dt

    # If less than a minute ago
    if diff.total_seconds() < 60:
        return "just now"

    # If less than an hour ago
    elif diff.total_seconds() < 3600:
        minutes = int(diff.total_seconds() / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"

    # If today
    elif dt.date() == now.date():
        return f"today at {dt.strftime('%I:%M%p').lower()}"

    # If yesterday
    elif (now.date() - dt.date()).days == 1:
        return f"yesterday at {dt.strftime('%I:%M%p').lower()}"

    # If within the last week
    elif diff.days < 7:
        day_name = dt.strftime("%A")
        return f"{day_name} at {dt.strftime('%I:%M%p').lower()}"

    # Otherwise, use full date
    else:
        return dt.strftime("%B %d at %I:%M%p").lower()
