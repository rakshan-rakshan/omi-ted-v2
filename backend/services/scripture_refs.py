"""
Extract scripture references (book, chapter, verse) from Telugu text.
Uses a curated mapping of Telugu Bible book abbreviations.
"""
import re
from typing import List, Dict

# Telugu book name mappings (common abbreviations)
TELUGU_BOOKS: Dict[str, str] = {
    # Old Testament
    "ఆది": "Genesis", "నిర్గమ": "Exodus", "లేవీ": "Leviticus",
    "సంఖ్యా": "Numbers", "ద్వితీ": "Deuteronomy", "యెహో": "Joshua",
    "న్యాయా": "Judges", "రూతు": "Ruth", "1 సమూ": "1 Samuel",
    "2 సమూ": "2 Samuel", "1 రాజు": "1 Kings", "2 రాజు": "2 Kings",
    "1 దిన": "1 Chronicles", "2 దిన": "2 Chronicles", "ఎజ్రా": "Ezra",
    "నెహె": "Nehemiah", "ఎస్తే": "Esther", "యోబు": "Job",
    "కీర్త": "Psalms", "సామె": "Proverbs", "ప్రసం": "Ecclesiastes",
    "పరమ": "Song of Solomon", "యెష": "Isaiah", "యిర్మీ": "Jeremiah",
    "విలా": "Lamentations", "యెహె": "Ezekiel", "దాని": "Daniel",
    "హోషే": "Hosea", "యోవే": "Joel", "ఆమో": "Amos",
    "ఓబ": "Obadiah", "యోనా": "Jonah", "మీకా": "Micah",
    "నహూ": "Nahum", "హబ": "Habakkuk", "జెఫ": "Zephaniah",
    "హగ్గి": "Haggai", "జెక": "Zechariah", "మలా": "Malachi",
    # New Testament
    "మత్త": "Matthew", "మార్కు": "Mark", "లూకా": "Luke",
    "యోహా": "John", "అపో": "Acts", "రోమా": "Romans",
    "1 కొరి": "1 Corinthians", "2 కొరి": "2 Corinthians",
    "గలా": "Galatians", "ఎఫె": "Ephesians", "ఫిలి": "Philippians",
    "కొలో": "Colossians", "1 థెస": "1 Thessalonians",
    "2 థెస": "2 Thessalonians", "1 తిమో": "1 Timothy",
    "2 తిమో": "2 Timothy", "తీతు": "Titus", "ఫిలే": "Philemon",
    "హెబ్రీ": "Hebrews", "యాకో": "James", "1 పేతు": "1 Peter",
    "2 పేతు": "2 Peter", "1 యోహా": "1 John", "2 యోహా": "2 John",
    "3 యోహా": "3 John", "యూదా": "Jude", "ప్రక": "Revelation",
}

# Pattern: optional book name, then chapter:verse (e.g., "మత్త 5:3" or "ఆది 1:1-5")
_REF_PATTERN = re.compile(
    r'((?:[123]\s*)?[\u0C00-\u0C7F]{2,})\s*(\d{1,3})\s*[:\u0983]\s*(\d{1,3})(?:\s*[–\-]\s*(\d{1,3}))?',
    re.UNICODE
)


def extract_refs(text: str) -> List[Dict]:
    """Scan text for Telugu scripture references. Returns list of {book, chapter, verse}."""
    refs = []
    for match in _REF_PATTERN.finditer(text):
        book_te = match.group(1).strip()
        chapter = int(match.group(2))
        verse = int(match.group(3))
        verse_end = int(match.group(4)) if match.group(4) else None
        
        book_en = None
        for abbr, full in TELUGU_BOOKS.items():
            if book_te.startswith(abbr):
                book_en = full
                break
        
        if book_en:
            entry = {"book": book_en, "chapter": chapter, "verse": verse}
            if verse_end:
                entry["verse_end"] = verse_end
            refs.append(entry)
    
    return refs
