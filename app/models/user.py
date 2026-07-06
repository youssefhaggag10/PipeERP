from dataclasses import dataclass


@dataclass(frozen=True)
class User:
    id: int
    username: str
    full_name: str
    role: str

    @property
    def display_name(self) -> str:
        return self.full_name or self.username
