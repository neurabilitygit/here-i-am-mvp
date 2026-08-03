from __future__ import annotations

from datetime import date

DAILY_PROMPTS: list[str] = [
    "What's a smell that takes you right back to childhood?",
    'Tell me about a meal you will never forget.',
    'Who taught you something you still use today?',
    "What's the bravest thing you remember doing?",
    'Describe a place that felt like home.',
    'What made you laugh so hard you cried?',
    "Tell me about a friend you've lost touch with.",
    "What's a piece of advice you got that turned out to be right?",
    'Describe your first day at a job you remember well.',
    'What was playing on the radio during a memory you love?',
    'Tell me about a time you changed your mind about something important.',
    "What's a family story that gets told every year?",
    'Describe the house you grew up in.',
    'Who was the first person you fell in love with?',
    'What did you want to be when you were young?',
    'Tell me about a trip that did not go as planned.',
    "What's a skill you're proud of learning?",
    'Describe a teacher who mattered to you.',
    'What was the hardest goodbye you remember?',
    'Tell me about a time you helped someone unexpectedly.',
    "What's a tradition your family kept?",
    'Describe the best gift you ever gave or received.',
    'What was your neighborhood like growing up?',
    'Tell me about a mistake that taught you something.',
    "What's a sound that instantly calms you?",
    'Describe a moment you felt truly proud.',
    'Who made you feel most understood?',
    'Tell me about the first car you ever drove.',
    "What's a book or song that changed how you saw things?",
    'Describe a celebration you will never forget.',
]


def prompt_of_the_day(today: date | None = None) -> str:
    day_index = (today or date.today()).toordinal()
    return DAILY_PROMPTS[day_index % len(DAILY_PROMPTS)]
