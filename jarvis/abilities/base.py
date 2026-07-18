from typing import Protocol

from jarvis.abilities.metadata import AbilityMetadata


class Ability(Protocol):
    """Minimum callable contract for Jarvis abilities."""

    metadata: AbilityMetadata

    @property
    def id(self):
        """Return the stable ability ID."""
        ...

    @property
    def name(self):
        """Return the display ability name."""
        ...

    @property
    def type(self):
        """Return the ability execution type."""
        ...

    @property
    def description(self):
        """Return the ability description."""
        ...

    @property
    def permission(self):
        """Return the required permission level."""
        ...

    def execute(self, input_data):
        """Execute the ability and return an AbilityResult."""
        ...

    def health(self):
        """Return AbilityHealth for this ability and its provider."""
        ...
