"""The web intake package: search, crawl, evidence and the citation check.

One tool, ``core.tools.web_research``, is the caller. Nothing here makes a model
call and nothing opens a route of its own; the crawl reaches the network only
through ``core.net_guard``.
"""
from core.web_intake.crawl import CrawlGap, CrawlPage, CrawlRun, html_to_text
from core.web_intake.evidence import EvidenceSource, EvidenceStore
from core.web_intake.search import SearchConfig, SearchHit
from core.web_intake.search import search as search_web
from core.web_intake.verify import Verification, verify_answer

__all__ = [
    "CrawlGap",
    "CrawlPage",
    "CrawlRun",
    "EvidenceSource",
    "EvidenceStore",
    "SearchConfig",
    "SearchHit",
    "Verification",
    "html_to_text",
    "search_web",
    "verify_answer",
]
