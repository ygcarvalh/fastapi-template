from dataclasses import dataclass


@dataclass(frozen=True)
class Mail:
    to: str
    subject: str
    body: str
