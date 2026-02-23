import hashlib
import json


def compute_event_hash(event: dict, previous_hash: str, session_id: str) -> str:
    """Compute the _hash for a single event. Excludes _hash from payload."""
    payload = {k: v for k, v in event.items() if k != "_hash"}
    # Stable serialisation: sorted keys, no extra whitespace
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    hash_input   = payload_json + "|" + previous_hash + "|" + session_id
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()


def verify_process_log(log: dict) -> tuple[bool, str]:
    """
    Verify a TWFF process-log.json dict.
    Returns (is_valid: bool, detail_message: str).
    """
    session_id = log.get("session_id", "")
    events     = log.get("events", [])
    prev_hash  = ""

    for i, event in enumerate(events):
        stored_hash   = event.get("_hash", "")
        expected_hash = compute_event_hash(event, prev_hash, session_id)
        if stored_hash and stored_hash != expected_hash:
            return False, (
                f"Hash mismatch at event {i} (type={event.get('type')!r}). "
                f"Expected {expected_hash[:16]}…, got {stored_hash[:16]}…"
            )
        prev_hash = stored_hash or expected_hash

    # Verify top-level _integrity.head_hash if present
    integrity = log.get("_integrity", {})
    head_hash = integrity.get("head_hash", "")
    if head_hash and head_hash != prev_hash:
        return False, (
            f"_integrity.head_hash mismatch. "
            f"Expected {prev_hash[:16]}…, got {head_hash[:16]}…"
        )

    return True, f"Log intact — {len(events)} events verified."
