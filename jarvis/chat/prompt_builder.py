from dataclasses import dataclass
from enum import Enum


class PromptMode(str, Enum):
    """Define special modes that can shape Jarvis responses."""

    DEFAULT = "default"
    PROJECT = "project"
    DEVELOPER = "developer"
    JAPANESE = "japanese"
    HOTEL = "hotel"
    FINANCE = "finance"


@dataclass
class JarvisPromptProfile:
    """Store Jarvis identity, rules, personality, and mode instructions."""

    identity: list
    core_rules: list
    personality: list
    special_modes: dict


class PromptBuilder:
    """Build provider-ready prompts without depending on any provider."""

    def __init__(self, profile):
        """Create a prompt builder with one Jarvis prompt profile."""
        self.profile = profile

    def build(self, user_message, mode=PromptMode.DEFAULT):
        """Build the final prompt sent to a ChatProvider."""
        return (
            f"{format_section('Identity', self.profile.identity)}\n\n"
            f"{format_section('Core Rules', self.profile.core_rules)}\n\n"
            f"{format_section('Personality', self.profile.personality)}\n\n"
            f"{format_section('Special Mode', self.get_mode_rules(mode))}\n\n"
            f"User Message:\n{user_message}"
        )

    def get_mode_rules(self, mode):
        """Return special rules for one prompt mode."""
        return self.profile.special_modes.get(mode, self.profile.special_modes[PromptMode.DEFAULT])


def create_default_prompt_profile():
    """Create the default Jarvis prompt profile."""
    return JarvisPromptProfile(
        identity=[
            "Name: Jarvis",
            "Role: Personal AI Assistant",
            "Relationship: User's project assistant and daily companion",
        ],
        core_rules=[
            "Be honest.",
            "If something is unknown, say it is unknown.",
            "Clearly mark assumptions as assumptions.",
            "Do not exaggerate.",
            "Prefer practical, actionable answers.",
            "Keep responses concise unless detail is requested.",
        ],
        personality=[
            "Calm",
            "Warm",
            "Slightly witty",
            "Logical",
            "Supportive but not blindly flattering",
        ],
        special_modes={
            PromptMode.DEFAULT: [
                "Respond as Jarvis using the default assistant behavior.",
            ],
            PromptMode.PROJECT: [
                "When the user calls Jarvis PM, respond like a project manager.",
                "Focus on sprint, roadmap, priority, risk, architecture, and next action.",
            ],
            PromptMode.DEVELOPER: [
                "For coding and design questions, focus on architecture, maintainability, and future extensibility.",
            ],
            PromptMode.JAPANESE: [
                "For Japanese language help, output hiragana with spacing.",
                "Then output Japanese with kanji/kana.",
                "Then output Korean pronunciation.",
                "Then output Korean meaning.",
            ],
            PromptMode.HOTEL: [
                "For hotel and work questions, respond from a Front Office, AFOM, or DOR operations perspective.",
            ],
            PromptMode.FINANCE: [
                "For investment questions, explain risk clearly.",
                "Avoid hype.",
                "Mark assumptions.",
            ],
        },
    )


def format_section(title, lines):
    """Format a prompt section as a readable bullet list."""
    body = "\n".join([f"- {line}" for line in lines])
    return f"{title}:\n{body}"

