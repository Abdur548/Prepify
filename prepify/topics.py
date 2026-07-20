from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    code: str
    name: str
    tier: str

    @property
    def difficulty(self) -> str:
        return "Medium" if self.tier == "AS" else "Hard"

    @property
    def allowed_difficulties(self) -> tuple[str, ...]:
        return ("Easy", "Medium") if self.tier == "AS" else ("Medium", "Hard")


# Cambridge 9618 (2026) content-overview subsection taxonomy. Codes are stable
# identifiers; names are the student-facing topic tags used by the API.
TOPICS: tuple[Topic, ...] = (
    Topic("1.1", "Data Representation", "AS"),
    Topic("1.2", "Multimedia - Graphics, Sound", "AS"),
    Topic("1.3", "Compression", "AS"),
    Topic("2.1", "Networks including the internet", "AS"),
    Topic("3.1", "Computers and their components", "AS"),
    Topic("3.2", "Logic Gates and Logic Circuits", "AS"),
    Topic("4.1", "Central Processing Unit (CPU) Architecture", "AS"),
    Topic("4.2", "Assembly Language", "AS"),
    Topic("4.3", "Bit manipulation", "AS"),
    Topic("5.1", "Operating Systems", "AS"),
    Topic("5.2", "Language Translators", "AS"),
    Topic("6.1", "Data Security", "AS"),
    Topic("6.2", "Data Integrity", "AS"),
    Topic("7.1", "Ethics and Ownership", "AS"),
    Topic("8.1", "Database Concepts", "AS"),
    Topic("8.2", "Database Management Systems (DBMS)", "AS"),
    Topic("8.3", "Data Definition and Manipulation Languages", "AS"),
    Topic("9.1", "Computational Thinking Skills", "AS"),
    Topic("9.2", "Algorithms", "AS"),
    Topic("10.1", "Data Types and Records", "AS"),
    Topic("10.2", "Arrays", "AS"),
    Topic("10.3", "Files", "AS"),
    Topic("10.4", "Introduction to Abstract Data Types (ADT)", "AS"),
    Topic("11.1", "Programming Basics", "AS"),
    Topic("11.2", "Constructs", "AS"),
    Topic("11.3", "Structured Programming", "AS"),
    Topic("12.1", "Program Development Life cycle", "AS"),
    Topic("12.2", "Program Design", "AS"),
    Topic("12.3", "Program Testing and Maintenance", "AS"),
    Topic("13.1", "User-defined data types", "A2"),
    Topic("13.2", "File organisation and access", "A2"),
    Topic("13.3", "Floating-point representation and manipulation", "A2"),
    Topic("14.1", "Protocols", "A2"),
    Topic("14.2", "Circuit switching and packet switching", "A2"),
    Topic("15.1", "Processors, Parallel Processing and Virtual Machines", "A2"),
    Topic("15.2", "Boolean Algebra and Logic Circuits", "A2"),
    Topic("16.1", "Purposes of an Operating System (OS)", "A2"),
    Topic("16.2", "Translation Software", "A2"),
    Topic("17.1", "Encryption, Encryption Protocols and Digital certificates", "A2"),
    Topic("18.1", "Artificial Intelligence", "A2"),
    Topic("19.1", "Algorithms", "A2"),
    Topic("19.2", "Recursion", "A2"),
    Topic("20.1", "Programming Paradigms", "A2"),
    Topic("20.2", "File Processing and Exception Handling", "A2"),
)

TOPIC_BY_NAME = {topic.name.casefold(): topic for topic in TOPICS}
TOPIC_BY_CODE = {topic.code: topic for topic in TOPICS}


def resolve_topic(value: str) -> Topic:
    normalized = value.strip().casefold()
    topic = TOPIC_BY_CODE.get(value.strip()) or TOPIC_BY_NAME.get(normalized)
    if topic is None:
        raise ValueError(f"Unknown Cambridge 9618 topic tag: {value}")
    return topic
