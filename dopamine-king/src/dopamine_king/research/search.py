"""Federated study search: OpenAlex, Crossref and arXiv merged, de-duplicated and graded.

Each source is isolated: a failing one adds a message to the returned errors and the others
continue. Nothing here verifies a citation; results carry ``verified=False``.
"""
from __future__ import annotations

import dataclasses
from typing import Callable

from ..net import Fetcher
from .arxiv import ArxivClient, normalize_arxiv_id
from .crossref import CrossrefClient
from .grading import apply_grade
from .models import Study, normalize_title
from .openalex import OpenAlexClient
from .pubmed import PubMedClient

SOURCES = ("openalex", "crossref", "arxiv")
ALL_SOURCES = SOURCES + ("pubmed",)       # PubMed is opt-in: it is the right place for biomedical topics
_ARXIV_DOI_PREFIX = "10.48550/arxiv."      # DataCite DOIs minted for arXiv preprints
_MAX_PER_SOURCE = 50


def _is_preprint(study: Study) -> bool:
    return study.design == "preprint" or study.peer_reviewed is False


def dedupe_key(study: Study) -> str:
    """DOI when there is one, else the arXiv id, else the normalised title."""
    doi = study.doi
    if doi and doi.startswith(_ARXIV_DOI_PREFIX):
        arxiv_id = normalize_arxiv_id(doi[len(_ARXIV_DOI_PREFIX):])
        if arxiv_id:
            return f"arxiv:{arxiv_id}"
    if doi:
        return f"doi:{doi}"
    if study.id.startswith("arxiv:"):
        return study.id
    return f"title:{normalize_title(study.title)}"


def _group(studies: list[Study]) -> list[list[Study]]:
    """Group duplicates. A record without DOI joins any group with the same title; two DOIs with
    the same title are one work only when one of them is a preprint of the other."""
    groups: list[list[Study]] = []
    by_key: dict[str, int] = {}
    by_title: dict[str, list[int]] = {}
    for study in studies:
        key = dedupe_key(study)
        title = normalize_title(study.title)
        target = by_key.get(key)
        if target is None:
            for idx in by_title.get(title, []):
                if key.startswith("title:") or _is_preprint(study) or any(_is_preprint(g) for g in groups[idx]):
                    target = idx
                    break
        if target is None:
            groups.append([])
            target = len(groups) - 1
        groups[target].append(study)
        by_key[key] = target
        if target not in by_title.setdefault(title, []):
            by_title[title].append(target)
    return groups


def _merge(group: list[Study]) -> Study:
    """One record per work: the published version leads, gaps are filled from the others."""
    ranked = sorted(
        group,
        key=lambda s: (_is_preprint(s), s.doi is None, s.abstract is None, -(s.cited_by or 0)),
    )
    merged = dataclasses.replace(ranked[0], authors=list(ranked[0].authors))
    others = ranked[1:]
    for name in ("abstract", "venue", "url", "year", "doi"):
        if not getattr(merged, name):
            merged_value = next((getattr(o, name) for o in others if getattr(o, name)), None)
            if merged_value:
                setattr(merged, name, merged_value)
    if not merged.authors:
        merged.authors = next((list(o.authors) for o in others if o.authors), [])
    counts = [s.cited_by for s in group if s.cited_by is not None]
    merged.cited_by = max(counts) if counts else None
    if merged.design == "unknown":
        merged.design = next((o.design for o in others if o.design not in ("unknown", "preprint")), "unknown")
    if merged.peer_reviewed is None:
        merged.peer_reviewed = next((o.peer_reviewed for o in others if o.peer_reviewed is not None), None)
    merged.retracted = any(s.retracted for s in group)      # one source flagging it is enough
    return merged


def merge_studies(studies: list[Study]) -> list[Study]:
    return [_merge(g) for g in _group(studies)]


def _run_source(
    name: str, query: str, fetcher: Fetcher, *, size: int, mailto: str | None, year_from: int | None,
) -> list[Study]:
    runners: dict[str, Callable[[], list[Study]]] = {
        "openalex": lambda: OpenAlexClient(fetcher, mailto).search(query, per_page=size, year_from=year_from),
        "crossref": lambda: CrossrefClient(fetcher, mailto).search(query, rows=size),
        "arxiv": lambda: ArxivClient(fetcher).search(query, max_results=size),
        "pubmed": lambda: PubMedClient(fetcher, mailto).search(query, retmax=size, year_from=year_from),
    }
    if name not in runners:
        raise ValueError(f"unknown source {name!r}")
    return runners[name]()


def search_studies(
    query: str,
    fetcher: Fetcher,
    *,
    sources: tuple[str, ...] = SOURCES,
    limit: int = 10,
    mailto: str | None = None,
    year_from: int | None = None,
) -> tuple[list[Study], list[str]]:
    """Search every source, merge duplicates, grade and rank. Returns ``(studies[:limit], errors)``."""
    errors: list[str] = []
    if not query or not query.strip():
        return [], ["empty query"]
    size = max(1, min(max(limit, 10), _MAX_PER_SOURCE))
    collected: list[Study] = []
    for name in dict.fromkeys(sources):
        try:
            collected.extend(_run_source(name, query.strip(), fetcher, size=size, mailto=mailto, year_from=year_from))
        except Exception as err:  # noqa: BLE001 - one broken source must never sink the others
            errors.append(f"{name}: {type(err).__name__}: {err}")
    studies = merge_studies(collected)
    if year_from is not None:
        studies = [s for s in studies if s.year is not None and s.year >= year_from]
    for study in studies:
        apply_grade(study)
    studies.sort(key=lambda s: (-s.grade_score, -(s.cited_by or 0), -(s.year or 0), s.title.lower(), s.id))
    return studies[: max(0, limit)], errors
