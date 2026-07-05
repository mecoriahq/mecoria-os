def clean_output(text: str) -> str:
    """
    Basic output cleanup.

    Future versions will:
    - Validate structure
    - Convert to JSON
    - Export to Notion
    - Remove hallucinations
    """

    return text.strip()