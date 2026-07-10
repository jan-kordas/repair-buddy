import re

# Elektroda video player boilerplate injected when posts contain embedded videos
_VIDEO_PLAYER = re.compile(
    r"Video Player is loading\..*?(?=\n\n|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_VIDEO_SIMPLE = re.compile(r"\bVideo\s*\n", re.IGNORECASE)

# UI button labels scraped alongside post content
_UI_LABELS = re.compile(
    r"\b(Play|Pause|Mute|Unmute|Current Time|Duration|Loaded|Stream Type|"
    r"Seek to live|Remaining Time|Playback Rate|Chapters|Fullscreen|"
    r"Odtwórz|Zatrzymaj|Wycisz|Pokaż więcej|Załadowano)\b.*?\n",
    re.IGNORECASE,
)

# Timestamp artifacts: "Dodano po X minutach:" / "Edytowano:"
_EDIT_STAMPS = re.compile(
    r"(Dodano po \d+.*?:|Edytowano.*?:|Ostatnio edytowane.*?:)\s*",
    re.IGNORECASE,
)

# Elektroda quote blocks: "Użytkownik X napisał:" followed by quoted line
_QUOTE_HEADER = re.compile(
    r"[^\n]+napisał[aą]?:\s*\n",
    re.IGNORECASE,
)

# Decorative / semantic-noise emoji (keep alphanumeric punctuation)
def _is_noise_char(ch: str) -> bool:
    cp = ord(ch)
    # Emoji ranges
    if 0x1F300 <= cp <= 0x1FFFF:
        return True
    # Misc symbols & dingbats
    if 0x2600 <= cp <= 0x27BF:
        return True
    # Enclosed alphanumeric supplement (circled letters/numbers)
    if 0x1F100 <= cp <= 0x1F1FF:
        return True
    return False


def strip_emoji(text: str) -> str:
    return "".join(ch for ch in text if not _is_noise_char(ch))


def clean_post(content: str) -> str:
    text = content
    text = _VIDEO_PLAYER.sub("", text)
    text = _VIDEO_SIMPLE.sub("", text)
    text = _UI_LABELS.sub("", text)
    text = _EDIT_STAMPS.sub("", text)
    text = _QUOTE_HEADER.sub("", text)
    text = strip_emoji(text)
    # Collapse runs of blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_summary(summary: str) -> str:
    """Remove decorative prefix emoji (✨ etc.) from ai_summary."""
    text = strip_emoji(summary)
    return text.strip()
