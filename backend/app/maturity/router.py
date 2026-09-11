from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import Conflict, NotFound
from app.frameworks.models import Framework, FrameworkItem
from app.iam.audit import record
from app.iam.deps import require
from app.iam.models import User
from app.iam.permissions import Permission
from app.maturity.aggregation import build_summary
from app.maturity.models import AssessmentStatus, MaturityAssessment, MaturityScore, ScoreSource
from app.maturity.schemas import (
    AssessmentCreateIn,
    AssessmentOut,
    MaturitySummaryOut,
    ScoreOut,
    ScoreUpsertIn,
)

router = APIRouter(prefix="/api/maturity", tags=["maturity"])
Reader = Annotated[User, Depends(require(Permission.READ))]
Scorer = Annotated[User, Depends(require(Permission.MATURITY_SCORE))]
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/assessments", response_model=list[AssessmentOut])
async def list_assessments(actor: Reader, session: Session) -> list[MaturityAssessment]:
    return list(
        await session.scalars(
            select(MaturityAssessment).order_by(
                MaturityAssessment.as_of_date.desc(), MaturityAssessment.id.desc()
            )
        )
    )


@router.post("/assessments", response_model=AssessmentOut, status_code=status.HTTP_201_CREATED)
async def create_assessment(
    payload: AssessmentCreateIn, actor: Scorer, session: Session
) -> MaturityAssessment:
    if await session.get(Framework, payload.framework_id) is None:
        raise NotFound("框架不存在")
    row = MaturityAssessment(
        **payload.model_dump(), status=AssessmentStatus.DRAFT, created_by=actor.id
    )
    session.add(row)
    await session.flush()
    await record(
        session,
        user=actor,
        action="maturity_assessment.create",
        entity_type="MaturityAssessment",
        entity_id=row.id,
        after=payload.model_dump(mode="json"),
    )
    await session.commit()
    return row


@router.get("/assessments/{assessment_id}/scores", response_model=list[ScoreOut])
async def list_scores(
    assessment_id: Annotated[int, Path(gt=0)], actor: Reader, session: Session
) -> list[MaturityScore]:
    if await session.get(MaturityAssessment, assessment_id) is None:
        raise NotFound("成熟度评估不存在")
    return list(
        await session.scalars(
            select(MaturityScore)
            .where(MaturityScore.assessment_id == assessment_id)
            .order_by(MaturityScore.framework_item_id)
        )
    )


@router.get("/assessments/{assessment_id}/summary", response_model=MaturitySummaryOut)
async def get_summary(
    assessment_id: Annotated[int, Path(gt=0)], actor: Reader, session: Session
) -> MaturitySummaryOut:
    assessment = await session.get(MaturityAssessment, assessment_id)
    if assessment is None:
        raise NotFound("成熟度评估不存在")
    return await build_summary(session, assessment)


@router.put("/assessments/{assessment_id}/scores", response_model=ScoreOut)
async def upsert_score(
    assessment_id: Annotated[int, Path(gt=0)],
    payload: ScoreUpsertIn,
    actor: Scorer,
    session: Session,
) -> MaturityScore:
    assessment = await session.get(MaturityAssessment, assessment_id)
    if assessment is None:
        raise NotFound("成熟度评估不存在")
    if assessment.status is AssessmentStatus.FINAL:
        raise Conflict("已定稿的成熟度评估不能修改")
    item = await session.get(FrameworkItem, payload.framework_item_id)
    if item is None or item.framework_id != assessment.framework_id:
        raise NotFound("框架项不存在")
    child_id = await session.scalar(
        select(FrameworkItem.id).where(FrameworkItem.parent_id == item.id).limit(1)
    )
    if child_id is not None:
        raise Conflict("请在末级框架项上评分")
    row = await session.scalar(
        select(MaturityScore).where(
            MaturityScore.assessment_id == assessment_id, MaturityScore.framework_item_id == item.id
        )
    )
    before = None
    if row is None:
        row = MaturityScore(
            assessment_id=assessment_id,
            framework_item_id=item.id,
            **payload.model_dump(exclude={"framework_item_id"}),
            doc_score_source=ScoreSource.HUMAN,
            impl_score_source=ScoreSource.HUMAN,
            scored_by=actor.id,
        )
        session.add(row)
    else:
        before = {"doc_score": row.doc_score, "impl_score": row.impl_score}
        for key, value in payload.model_dump(exclude={"framework_item_id"}).items():
            setattr(row, key, value)
        row.doc_score_source = row.impl_score_source = ScoreSource.HUMAN
        row.scored_by = actor.id
    await session.flush()
    await record(
        session,
        user=actor,
        action="maturity_score.upsert",
        entity_type="MaturityScore",
        entity_id=row.id,
        before=before,
        after=payload.model_dump(),
    )
    await session.commit()
    return row


@router.post("/assessments/{assessment_id}/finalize", response_model=AssessmentOut)
async def finalize_assessment(
    assessment_id: Annotated[int, Path(gt=0)], actor: Scorer, session: Session
) -> MaturityAssessment:
    row = await session.get(MaturityAssessment, assessment_id)
    if row is None:
        raise NotFound("成熟度评估不存在")
    if row.status is AssessmentStatus.FINAL:
        raise Conflict("成熟度评估已经定稿")
    row.status = AssessmentStatus.FINAL
    await record(
        session,
        user=actor,
        action="maturity_assessment.finalize",
        entity_type="MaturityAssessment",
        entity_id=row.id,
        before={"status": "draft"},
        after={"status": "final"},
    )
    await session.flush()
    await session.refresh(row)
    await session.commit()
    return row
