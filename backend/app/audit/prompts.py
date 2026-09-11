ANSWER_TASK_KEY = "answer_generation"

ANSWER_SYSTEM = """You draft audit responses using only the supplied internal evidence.
Never invent a policy, implementation, owner, tool, or evidence item. Select only clause IDs from
the supplied sources; the application will attach verified verbatim excerpts after generation.
If the sources do not fully answer the question, say so in gap_notes and keep the answer qualified.
Return only JSON matching the schema. Write body and gap_notes in the requested language."""

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "body": {"type": "string", "minLength": 1},
        "language": {"type": "string", "enum": ["zh", "en"]},
        "citations": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "clause_id": {"type": "integer", "minimum": 1},
                },
                "required": ["clause_id"],
                "additionalProperties": False,
            },
        },
        "cited_control_ids": {"type": "array", "items": {"type": "integer"}},
        "suggested_evidence_ids": {"type": "array", "items": {"type": "integer"}},
        "gap_notes": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": [
        "body",
        "language",
        "citations",
        "cited_control_ids",
        "suggested_evidence_ids",
        "gap_notes",
        "confidence",
    ],
    "additionalProperties": False,
}
