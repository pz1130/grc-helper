import pytest

from app.clauses.models import Clause, ClauseChunk
from app.ingest.models import DocType, Document
from app.search.fulltext import search


async def _chunks(db_session, bodies: list[str], *, doc_title: str = "P") -> Document:
    doc = Document(
        title=doc_title, doc_type=DocType.PROCEDURE,
        file_hash=doc_title.ljust(64, "x"), file_path="/x.pdf", original_filename="x.pdf",
    )
    db_session.add(doc)
    await db_session.flush()
    clause = Clause(
        document_id=doc.id, number="1", heading="S", heading_path="Doc › S",
        citation_label="1", text="", order_index=0, level=1,
    )
    db_session.add(clause)
    await db_session.flush()
    for index, body in enumerate(bodies):
        db_session.add(
            ClauseChunk(
                clause_id=clause.id, document_id=doc.id, chunk_index=index, text=body
            )
        )
    await db_session.flush()
    return doc


@pytest.mark.asyncio
async def test_finds_a_matching_chunk(db_session):
    await _chunks(db_session, ["Privileged accounts must be reviewed quarterly."])
    hits = await search(db_session, "privileged account review")
    assert len(hits) == 1


@pytest.mark.asyncio
async def test_ranks_are_dense_and_start_at_one(db_session):
    await _chunks(
        db_session,
        [
            "Privileged access management with VaultKeeper.",
            "Privileged accounts and privileged access reviews.",
            "Change management process.",
        ],
    )
    hits = await search(db_session, "privileged access")
    assert [h.rank for h in hits] == list(range(1, len(hits) + 1))


@pytest.mark.asyncio
async def test_stemming_matches_word_forms(db_session):
    await _chunks(db_session, ["Accounts are reviewed by the owner."])
    assert await search(db_session, "review") != []


@pytest.mark.asyncio
async def test_no_match_returns_empty(db_session):
    await _chunks(db_session, ["Change management process."])
    assert await search(db_session, "kubernetes") == []


@pytest.mark.asyncio
async def test_quoted_phrase_is_honoured(db_session):
    await _chunks(
        db_session,
        ["privileged access management", "access is privileged only in emergencies"],
    )
    hits = await search(db_session, '"privileged access"')
    assert len(hits) == 1


@pytest.mark.asyncio
async def test_negation_is_honoured(db_session):
    await _chunks(db_session, ["privileged access with VaultKeeper", "privileged access manual"])
    hits = await search(db_session, "privileged -vaultkeeper")
    assert len(hits) == 1


@pytest.mark.asyncio
async def test_document_filter_narrows_results(db_session):
    first = await _chunks(db_session, ["privileged access one"], doc_title="A")
    await _chunks(db_session, ["privileged access two"], doc_title="B")
    hits = await search(db_session, "privileged access", document_id=first.id)
    assert len(hits) == 1


@pytest.mark.asyncio
async def test_limit_is_respected(db_session):
    await _chunks(db_session, [f"privileged access number {i}" for i in range(10)])
    assert len(await search(db_session, "privileged", limit=3)) == 3


@pytest.mark.asyncio
async def test_empty_query_returns_empty_without_touching_the_database(db_session):
    await _chunks(db_session, ["privileged access"])
    assert await search(db_session, "   ") == []
