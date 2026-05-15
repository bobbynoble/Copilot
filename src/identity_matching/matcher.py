"""
NHS patient identity matching — tiered deterministic algorithm.

Tier 1: NHS Number exact match (Modulus 11 validated on both sides).
Tier 2: Demographic match — surname (Soundex), forename initial, DOB
        (with day/month swap tolerance), sex.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Optional

from .models import MatchDecision, MatchResult, MatchTier, PatientRecord
from .nhs_number import validate_nhs_number
from .phonetics import soundex


# ---------------------------------------------------------------------------
# Pairwise matching
# ---------------------------------------------------------------------------

def match_records(a: PatientRecord, b: PatientRecord) -> MatchResult:
    """Compare two patient records and return a MatchResult."""

    tier1 = _tier1_nhs(a, b)
    if tier1 is not None:
        return tier1

    return _tier2_demographic(a, b)


def _tier1_nhs(a: PatientRecord, b: PatientRecord) -> Optional[MatchResult]:
    """Return a result if both records have validated NHS Numbers, else None."""
    if not (validate_nhs_number(a.nhs_number) and validate_nhs_number(b.nhs_number)):
        return None

    if a.nhs_number == b.nhs_number:
        return MatchResult(
            record_a=a,
            record_b=b,
            decision=MatchDecision.MATCH,
            tier=MatchTier.NHS_NUMBER,
            matched_fields=["nhs_number"],
        )

    return MatchResult(
        record_a=a,
        record_b=b,
        decision=MatchDecision.NO_MATCH,
        tier=MatchTier.NHS_NUMBER,
        matched_fields=[],
        notes="Both records have valid but different NHS Numbers.",
    )


def _tier2_demographic(a: PatientRecord, b: PatientRecord) -> MatchResult:
    """
    Probabilistic-style deterministic demographic match.

    Rules:
    - surname Soundex must agree
    - forename initial must agree (if both present)
    - DOB must agree (day/month swap is accepted as a near-match)
    - sex must agree (if both present and not unknown)

    All four criteria must pass for a MATCH.
    Missing/unknown fields are skipped (not counted as failures).
    A DOB day/month swap is a POTENTIAL_DUPLICATE, not a MATCH.
    """
    matched: list[str] = []
    notes: list[str] = []
    swapped_dob = False

    # Surname via Soundex
    sx_a = soundex(a.surname)
    sx_b = soundex(b.surname)
    if not sx_a or not sx_b:
        return _no_match(a, b, "Insufficient demographic data (no surname).")
    if sx_a != sx_b:
        return _no_match(a, b)
    matched.append("surname_soundex")

    # Forename initial
    if a.forename and b.forename:
        if a.forename[0] != b.forename[0]:
            return _no_match(a, b)
        matched.append("forename_initial")

    # Date of birth
    dob_result = _compare_dob(a.date_of_birth, b.date_of_birth)
    if dob_result == "no_match":
        return _no_match(a, b)
    if dob_result == "exact":
        matched.append("date_of_birth")
    elif dob_result == "swapped":
        matched.append("date_of_birth_swapped")
        notes.append("DOB day/month transposition detected.")
        swapped_dob = True

    # Sex
    if a.sex and b.sex and a.sex != "U" and b.sex != "U":
        if a.sex != b.sex:
            return _no_match(a, b)
        matched.append("sex")

    decision = MatchDecision.POTENTIAL_DUPLICATE if swapped_dob else MatchDecision.MATCH
    return MatchResult(
        record_a=a,
        record_b=b,
        decision=decision,
        tier=MatchTier.DEMOGRAPHIC,
        matched_fields=matched,
        notes=" ".join(notes),
    )


def _compare_dob(
    dob_a: Optional[date], dob_b: Optional[date]
) -> str:
    """Return 'exact', 'swapped', 'no_match', or 'skip' (if either is None)."""
    if dob_a is None or dob_b is None:
        return "skip"
    if dob_a == dob_b:
        return "exact"
    # Day/month transposition
    try:
        swapped = date(dob_a.year, dob_a.day, dob_a.month)
        if swapped == dob_b:
            return "swapped"
    except ValueError:
        pass
    return "no_match"


def _no_match(a: PatientRecord, b: PatientRecord, notes: str = "") -> MatchResult:
    return MatchResult(
        record_a=a,
        record_b=b,
        decision=MatchDecision.NO_MATCH,
        tier=MatchTier.DEMOGRAPHIC,
        matched_fields=[],
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Bulk deduplication
# ---------------------------------------------------------------------------

class MatchGroup:
    """A cluster of records believed to represent the same patient."""

    def __init__(self, records: list[PatientRecord], pairs: list[MatchResult]):
        self.records = records
        self.pairs = pairs

    def __repr__(self) -> str:
        ids = [(r.source_system, r.local_id) for r in self.records]
        return f"MatchGroup(size={len(self.records)}, records={ids})"


class IdentityMatcher:
    """
    Matches and deduplicates patient records from one or more PAS systems.

    Usage:
        matcher = IdentityMatcher()
        groups = matcher.find_duplicates(records)
    """

    def find_duplicates(
        self,
        records: list[PatientRecord],
        include_no_match: bool = False,
    ) -> list[MatchGroup]:
        """
        Cluster records into groups of likely duplicates.

        Uses blocking on (DOB year, surname Soundex first char) to avoid
        O(n²) comparisons, then runs pairwise matching within each block.

        Parameters
        ----------
        records:
            All patient records to deduplicate.
        include_no_match:
            If True, singleton records (no match found) are also returned
            as single-record MatchGroups.

        Returns
        -------
        List of MatchGroups, each containing records believed to be the
        same patient. Sorted descending by group size.
        """
        pairs = self._compare_within_blocks(records)

        # Union-Find to cluster matched records
        parent = {id(r): id(r) for r in records}
        record_map = {id(r): r for r in records}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            parent[find(x)] = find(y)

        matched_pairs: list[MatchResult] = []
        for result in pairs:
            if result.decision in (MatchDecision.MATCH, MatchDecision.POTENTIAL_DUPLICATE):
                union(id(result.record_a), id(result.record_b))
                matched_pairs.append(result)

        # Build clusters
        clusters: dict[int, list[PatientRecord]] = defaultdict(list)
        for r in records:
            clusters[find(id(r))].append(r)

        # Map root → pairs
        pair_map: dict[int, list[MatchResult]] = defaultdict(list)
        for result in matched_pairs:
            root = find(id(result.record_a))
            pair_map[root].append(result)

        groups: list[MatchGroup] = []
        for root, cluster_records in clusters.items():
            if len(cluster_records) == 1 and not include_no_match:
                continue
            groups.append(MatchGroup(records=cluster_records, pairs=pair_map[root]))

        groups.sort(key=lambda g: len(g.records), reverse=True)
        return groups

    def compare_all(self, records: list[PatientRecord]) -> list[MatchResult]:
        """Return all pairwise MatchResults (including NO_MATCH) within blocks."""
        return self._compare_within_blocks(records)

    def _compare_within_blocks(self, records: list[PatientRecord]) -> list[MatchResult]:
        blocks: dict[tuple, list[PatientRecord]] = defaultdict(list)
        for r in records:
            for key in _blocking_keys(r):
                blocks[key].append(r)

        seen: set[frozenset] = set()
        results: list[MatchResult] = []

        for block_records in blocks.values():
            for i, a in enumerate(block_records):
                for b in block_records[i + 1:]:
                    pair_id = frozenset({id(a), id(b)})
                    if pair_id in seen:
                        continue
                    seen.add(pair_id)
                    results.append(match_records(a, b))

        return results


def _blocking_keys(r: PatientRecord) -> list[tuple]:
    """
    Return blocking keys for a record.

    A record can belong to multiple blocks to handle edge cases.
    """
    keys = []

    # Block by validated NHS Number alone (one-record blocks are skipped in
    # comparison, but they ensure NHS-number pairs are always found)
    if validate_nhs_number(r.nhs_number):
        keys.append(("nhs", r.nhs_number))

    # Demographic block: DOB year + first Soundex char of surname
    if r.date_of_birth and r.surname:
        sx = soundex(r.surname)
        if sx:
            keys.append(("demo", r.date_of_birth.year, sx[0]))

    # Fallback so records with only partial data still get a block
    if not keys:
        keys.append(("unblocked", r.source_system))

    return keys
