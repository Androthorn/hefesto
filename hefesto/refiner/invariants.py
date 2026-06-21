def check_invariants(candidate: str, invariants: list[str]) -> bool:
    return all(inv in candidate for inv in invariants)
