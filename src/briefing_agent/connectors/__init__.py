"""Connector abstraction layer.

All connectors produce MessageEnvelope objects and consume nothing else
from the triage pipeline. This keeps the LLM core untouched when
adding new mail sources (IMAP, Gmail, Outlook).
"""
